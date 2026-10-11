"use client";
import { useState, useEffect, useRef, useCallback } from "react";
import Link from "next/link";
import { competencyLabel } from "@/lib/competency-label";
import {
  Clock,
  Check,
  ChevronLeft,
  ChevronRight,
  ShieldCheck,
  ArrowRight,
  Cloud,
  AlertCircle,
  Home,
  Briefcase,
  FileText,
  FlaskConical,
  History,
  LockKeyhole,
} from "lucide-react";
import {
  api,
  post,
  put,
  Attempt,
  Dict,
  specName,
  gradeName,
  date,
  ApiError,
} from "@/lib/api";
import {
  answerPresent,
  captureAnswers,
  CapturedReview,
  ReviewReceipt,
  validateReviewReceipt,
  reviewSubmissionAllowed,
  reviewedSubmitBody,
} from "@/lib/assessment-review";
import {
  assessmentKind,
  certifiesGrade as hasGradeConfirmation,
} from "@/lib/assessment-scope";
import {
  Brand,
  Button,
  Badge,
  Loading,
  ErrorBox,
  Modal,
  Notice,
  Empty,
} from "@/components/ui";

const examNavigation = [
  { href: "/workspace/passport", label: "Паспорт", icon: FileText },
  { href: "/workspace/jobs", label: "Вакансии", icon: Briefcase },
  { href: "/workspace/practice", label: "Практика", icon: FlaskConical },
  { href: "/workspace/history", label: "История", icon: History },
  { href: "/workspace/privacy", label: "Приватность", icon: LockKeyhole },
];

function ExamSidebar({
  blocked = false,
  active = false,
  onNavigate,
}: {
  blocked?: boolean;
  active?: boolean;
  onNavigate?: (event: { preventDefault: () => void }) => void;
}) {
  return (
    <aside
      className="exam-sidebar v-exam-navigation"
      onClickCapture={onNavigate}
    >
      <div className="exam-sidebar-brand" aria-disabled={blocked || undefined}>
        <Brand />
      </div>
      <div className="exam-sidebar-section">Рабочая область</div>
      <nav aria-label="Навигация участника">
        {examNavigation.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className="exam-nav-link"
            aria-disabled={blocked || undefined}
            tabIndex={blocked ? -1 : undefined}
            onNavigate={onNavigate}
          >
            <Icon size={16} />
            {label}
          </Link>
        ))}
      </nav>
      <div className="exam-sidebar-footer">
        <p className="exam-nav-state" role="status">
          {blocked
            ? "Сначала дождись сохранения ответа или закрой проверку перед переходом."
            : active
              ? "Переход не останавливает серверный таймер. Попытку можно продолжить из истории."
              : "Сохранённые попытки доступны в твоей истории."}
        </p>
      </div>
    </aside>
  );
}

export function Exam({ id }: { id: string }) {
  const [attempt, setAttempt] = useState<Attempt | null>(null);
  const [answers, setAnswers] = useState<Record<string, unknown>>({});
  const [index, setIndex] = useState(0);
  const [error, setError] = useState<unknown>();
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [reviewing, setReviewing] = useState(false);
  const [review, setReview] = useState<CapturedReview | null>(null);
  const [reviewError, setReviewError] = useState<unknown>();
  const [allowMissing, setAllowMissing] = useState(false);
  const [remaining, setRemaining] = useState(0);
  const [lastSaved, setLastSaved] = useState("");
  const answersRef = useRef(answers);
  const dirtyRef = useRef(false);
  const versionRef = useRef(0);
  const saveRef = useRef(false);
  const savePending = useRef<Promise<unknown> | null>(null);
  const reviewRef = useRef(false);
  const reviewGeneration = useRef(0);
  const submittedRef = useRef(false);
  useEffect(
    () => () => {
      reviewGeneration.current++;
    },
    [id],
  );
  const load = useCallback(async () => {
    try {
      const a = await api<Attempt>(`/assessments/${id}`);
      setAttempt(a);
      setAnswers(a.answers || {});
      answersRef.current = a.answers || {};
      setError(undefined);
    } catch (e) {
      setError(e);
    }
  }, [id]);
  useEffect(() => {
    void load();
  }, [load]);
  const save = useCallback(async () => {
    if (
      saveRef.current ||
      reviewRef.current ||
      !dirtyRef.current ||
      submittedRef.current
    )
      return;
    saveRef.current = true;
    setSaving(true);
    const sentVersion = versionRef.current;
    try {
      const pending = put(`/assessments/${id}/answers`, {
        answers: answersRef.current,
      });
      savePending.current = pending;
      await pending;
      if (versionRef.current === sentVersion) {
        dirtyRef.current = false;
        setDirty(false);
      }
      setLastSaved(
        new Date().toLocaleTimeString("ru-RU", {
          hour: "2-digit",
          minute: "2-digit",
        }),
      );
      setError(undefined);
    } catch (e) {
      if (!submittedRef.current) setError(e);
    } finally {
      saveRef.current = false;
      savePending.current = null;
      setSaving(false);
    }
  }, [id]);
  useEffect(() => {
    if (!dirty || saving || confirm || error !== undefined) return;
    const timer = setTimeout(() => void save(), 900);
    return () => clearTimeout(timer);
  }, [answers, dirty, save, saving, confirm, error]);
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (dirtyRef.current) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, []);
  useEffect(() => {
    if (!attempt || attempt.result) return;
    const tick = () =>
      setRemaining(
        Math.max(
          0,
          Math.floor(
            (new Date(attempt.expires_at).getTime() - Date.now()) / 1000,
          ),
        ),
      );
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [attempt]);
  useEffect(() => {
    if (
      attempt &&
      attempt.status === "in_progress" &&
      remaining === 0 &&
      Date.now() >= new Date(attempt.expires_at).getTime()
    )
      void load();
  }, [remaining, attempt?.status, load]);
  const beginReview = useCallback(async () => {
    if (submittedRef.current || reviewing) return;
    const request = ++reviewGeneration.current;
    const version = versionRef.current;
    reviewRef.current = true;
    setConfirm(true);
    setReview(null);
    setAllowMissing(false);
    setReviewError(undefined);
    setReviewing(true);
    try {
      const captured = captureAnswers(answersRef.current);
      // Finish an older autosave first, then persist exactly the reviewed
      // snapshot. A failed old request never substitutes for this fresh write.
      if (savePending.current) {
        try {
          await savePending.current;
        } catch {
          /* fresh write below */
        }
      }
      if (request !== reviewGeneration.current) return;
      await put(`/assessments/${id}/answers`, { answers: captured });
      if (request !== reviewGeneration.current) return;
      if (versionRef.current === version) {
        dirtyRef.current = false;
        setDirty(false);
      }
      setLastSaved(
        new Date().toLocaleTimeString("ru-RU", {
          hour: "2-digit",
          minute: "2-digit",
        }),
      );
      setError(undefined);
      const receipt = await post<ReviewReceipt>(`/assessments/${id}/review`, {
        answers: captured,
      });
      if (request !== reviewGeneration.current) return;
      validateReviewReceipt(receipt);
      if (versionRef.current !== version)
        throw new Error(
          "Черновик изменился. Повтори проверку перед отправкой.",
        );
      setReview({ answers: captured, receipt, version });
    } catch (e) {
      if (request === reviewGeneration.current) {
        setReviewError(e);
        if (e instanceof ApiError && e.code === "ATTEMPT_CLOSED") {
          reviewRef.current = false;
          setConfirm(false);
          await load();
        }
      }
    } finally {
      if (request === reviewGeneration.current) setReviewing(false);
    }
  }, [id, reviewing, load]);
  const closeReview = () => {
    if (reviewing || submitting) return;
    reviewGeneration.current++;
    reviewRef.current = false;
    setConfirm(false);
    setReview(null);
    setReviewError(undefined);
  };
  const submit = useCallback(async () => {
    if (
      submittedRef.current ||
      reviewing ||
      !reviewSubmissionAllowed(review, allowMissing)
    )
      return;
    if (!review || review.version !== versionRef.current) {
      setReview(null);
      setReviewError(
        new Error("Черновик изменился. Повтори проверку перед отправкой."),
      );
      return;
    }
    submittedRef.current = true;
    setSubmitting(true);
    setReviewError(undefined);
    try {
      const response = await post<Dict>(
        `/assessments/${id}/submit`,
        reviewedSubmitBody(review, allowMissing),
      );
      dirtyRef.current = false;
      setDirty(false);
      setConfirm(false);
      reviewRef.current = false;
      if (response.items && response.id) setAttempt(response as Attempt);
      else await load();
    } catch (e) {
      setReviewError(e);
      submittedRef.current = false;
      if (
        e instanceof ApiError &&
        [
          "REVIEW_STALE",
          "ASSESSMENT_ANSWER_INVALID",
          "ASSESSMENT_INCOMPLETE",
        ].includes(e.code)
      )
        setReview(null);
      if (e instanceof ApiError && e.code === "ATTEMPT_CLOSED") {
        reviewRef.current = false;
        setConfirm(false);
        await load();
      }
    } finally {
      setSubmitting(false);
    }
  }, [id, load, review, reviewing, allowMissing]);
  const update = (value: unknown) => {
    if (!attempt || reviewRef.current || submittedRef.current) return;
    const next = { ...answers, [attempt.items[index].id]: value };
    setAnswers(next);
    answersRef.current = next;
    dirtyRef.current = true;
    versionRef.current++;
    setDirty(true);
  };
  const navigationPending =
    dirty || saving || reviewing || submitting || confirm;
  const guardNavigation = (event: { preventDefault: () => void }) => {
    if (
      navigationPending ||
      dirtyRef.current ||
      saveRef.current ||
      savePending.current ||
      reviewRef.current ||
      submittedRef.current
    )
      event.preventDefault();
  };
  if (error !== undefined && !attempt)
    return (
      <main className="exam-layout v-exam">
        <ExamSidebar />
        <section className="exam-surface v-exam-surface">
          <header className="exam-header v-exam-header">
            <span className="exam-breadcrumb">Проверка / Ошибка открытия</span>
            <Link
              className="button ghost exam-mobile-home"
              href="/workspace/passport"
            >
              <FileText size={15} /> Паспорт
            </Link>
          </header>
          <div className="linear-detail-main v-exam-main">
            <ErrorBox error={error} retry={() => void load()} />
            <Link className="link-action" href="/workspace/assessment">
              Вернуться к экзаменам <ChevronRight size={14} />
            </Link>
          </div>
        </section>
      </main>
    );
  if (!attempt)
    return (
      <main className="exam-layout v-exam">
        <ExamSidebar />
        <section className="exam-surface v-exam-surface">
          <header className="exam-header v-exam-header">
            <span className="exam-breadcrumb">
              Проверка / Открываем попытку
            </span>
            <Link
              className="button ghost exam-mobile-home"
              href="/workspace/passport"
            >
              <FileText size={15} /> Паспорт
            </Link>
          </header>
          <div className="linear-detail-main v-exam-main">
            <Loading label="Открываем сохранённую попытку" />
          </div>
        </section>
      </main>
    );
  const kind = assessmentKind(attempt);
  const needPractice = kind === "need_practice";
  if (attempt.result) return <ExamResult attempt={attempt} />;
  if (attempt.status === "expired")
    return (
      <main className="exam-layout v-exam">
        <ExamSidebar />
        <section className="exam-surface v-exam-surface">
          <header className="exam-header v-exam-header">
            <span className="exam-breadcrumb">Проверка / Попытка закрыта</span>
            <Link
              className="button ghost exam-mobile-home"
              href="/workspace/passport"
            >
              <FileText size={15} /> Паспорт
            </Link>
            <Link href="/workspace/history" className="button secondary">
              История экзаменов
            </Link>
          </header>
          <div className="linear-detail-main linear-document v-exam-main">
            <Badge>
              <Clock size={14} /> Попытка закрыта
            </Badge>
            <h1>Время этой попытки истекло</h1>
            <p>
              Сохранённые ответы остаются в истории. Сервер закрыл попытку;
              результат не присвоен. Подтверждённая ранее категория сохраняется.
            </p>
            <Link
              className="button primary"
              href={
                needPractice ? "/workspace/practice" : "/workspace/assessment"
              }
            >
              Выбрать следующий шаг <ArrowRight size={15} />
            </Link>
          </div>
        </section>
      </main>
    );
  const item = attempt.items[index];
  const answered = attempt.items.filter((q) =>
    answerPresent(answers[q.id]),
  ).length;
  const time = `${Math.floor(remaining / 60)
    .toString()
    .padStart(2, "0")}:${(remaining % 60).toString().padStart(2, "0")}`;
  return (
    <main className="exam-layout v-exam">
      <ExamSidebar
        active
        blocked={navigationPending}
        onNavigate={guardNavigation}
      />
      <section className="exam-surface v-exam-surface">
        <header className="exam-header v-exam-header">
          <span className="exam-breadcrumb">
            {needPractice ? "Практика" : "Проверка"} / Задание {index + 1} из{" "}
            {attempt.items.length}
          </span>
          <Link
            className="button ghost exam-mobile-home"
            href="/workspace/passport"
            aria-disabled={navigationPending || undefined}
            tabIndex={navigationPending ? -1 : undefined}
            onClick={guardNavigation}
            onNavigate={guardNavigation}
            title={
              navigationPending
                ? "Дождись сохранения ответа или закрой проверку"
                : "Паспорт компетенций"
            }
          >
            <FileText size={15} /> Паспорт
          </Link>
          <div
            className={`exam-timer ${remaining < 300 ? "warning" : ""}`}
            role="timer"
            aria-label={`Осталось ${Math.floor(remaining / 60)} минут ${remaining % 60} секунд`}
          >
            <Clock size={17} />
            {time}
          </div>
          <Button
            variant="secondary"
            onClick={() => void beginReview()}
            busy={submitting || reviewing}
            disabled={remaining === 0}
          >
            {needPractice ? "Завершить практику" : "Завершить экзамен"}
          </Button>
        </header>
        <div className="exam-body linear-detail-layout v-exam-body v-detail-layout">
          <div className="linear-detail-main v-exam-main">
            <div
              className="exam-question-content v-exam-question"
              aria-labelledby="exam-question-title"
            >
              <div className="v-exam-question-heading">
                <p className="v-exam-position" role="status">
                  Задание {index + 1} из {attempt.items.length}
                </p>
                <h1 id="exam-question-title">{item.title}</h1>
                <Badge>
                  {competencyLabel(item.competency_label || item.competency)}
                </Badge>
              </div>
              <div className="question-prompt v-exam-prompt">{item.prompt}</div>
              {remaining === 0 && (
                <Notice tone="amber">
                  Время истекло. Сервер закрывает попытку. Обнови страницу,
                  чтобы перейти к следующему шагу. Прежняя категория сохранится.
                </Notice>
              )}
              <AnswerEditor
                key={item.id}
                item={item}
                value={answers[item.id]}
                onChange={update}
                disabled={remaining === 0 || submitting || confirm}
              />
              {item.type === "sql" && (
                <div className="safe-data-note">
                  <ShieldCheck size={14} />
                  SQL выполняется на отдельном синтетическом наборе данных с
                  ограничениями. Произвольный код не запускается.
                </div>
              )}
              {error !== undefined && (
                <div className="top-gap">
                  <ErrorBox error={error} retry={() => void save()} />
                </div>
              )}
              <div className="exam-question-footer v-exam-actions">
                <Button
                  variant="secondary"
                  onClick={() => setIndex((i) => Math.max(0, i - 1))}
                  disabled={index === 0}
                >
                  <ChevronLeft size={15} /> Назад
                </Button>
                <span className="autosave v-exam-save-state" role="status">
                  {saving ? (
                    <Cloud size={13} />
                  ) : error ? (
                    <AlertCircle size={13} />
                  ) : (
                    <Check size={13} />
                  )}{" "}
                  {saving
                    ? "Сохраняем…"
                    : dirty
                      ? "Есть несохранённый ответ"
                      : lastSaved
                        ? `Сохранено ${lastSaved}`
                        : "Ответы восстановлены"}
                </span>
                {index < attempt.items.length - 1 ? (
                  <Button onClick={() => setIndex((i) => i + 1)}>
                    Далее <ChevronRight size={15} />
                  </Button>
                ) : (
                  <Button
                    onClick={() => void beginReview()}
                    disabled={remaining === 0}
                  >
                    К завершению <ArrowRight size={15} />
                  </Button>
                )}
              </div>
            </div>
          </div>
          <aside className="linear-exam-sidebar v-exam-inspector">
            <section className="panel">
              <h3>Попытка</h3>
              <dl className="linear-properties v-property-list">
                <div className="linear-property-row v-property-row">
                  <dt>Статус</dt>
                  <dd>{remaining === 0 ? "Время истекло" : "Активна"}</dd>
                </div>
                <div className="linear-property-row v-property-row">
                  <dt>Задание</dt>
                  <dd>
                    {index + 1} из {attempt.items.length}
                  </dd>
                </div>
                <div className="linear-property-row v-property-row">
                  <dt>Осталось</dt>
                  <dd>
                    <Clock size={14} />
                    {time}
                  </dd>
                </div>
                <div className="linear-property-row v-property-row">
                  <dt>{needPractice ? "Контекст" : "Категория"}</dt>
                  <dd>
                    {specName(attempt.specialization)} ·{" "}
                    {gradeName(attempt.grade)}
                  </dd>
                </div>
                <div className="linear-property-row v-property-row">
                  <dt>С ответом</dt>
                  <dd>
                    {answered} из {attempt.items.length}
                  </dd>
                </div>
              </dl>
            </section>
            <section className="panel" aria-labelledby="exam-map-heading">
              <h3 id="exam-map-heading">Задания</h3>
              <p className="v-exam-map-help">
                Возвращайся к любому заданию до завершения попытки. Отметка
                означает, что ответ заполнен.
              </p>
              <div
                className="question-dots v-exam-map"
                role="group"
                aria-label="Перейти к заданию"
              >
                {attempt.items.map((q, i) => (
                  <button
                    key={q.id}
                    onClick={() => setIndex(i)}
                    className={`${answerPresent(answers[q.id]) ? "answered" : ""} ${index === i ? "active" : ""}`}
                    aria-label={`Задание ${i + 1}${answerPresent(answers[q.id]) ? " — есть ответ" : ""}`}
                    aria-current={index === i ? "step" : undefined}
                  >
                    {i + 1}
                  </button>
                ))}
              </div>
            </section>
            <section className="panel linear-document">
              <h3>Рубрика и правила</h3>
              <p>
                Начальная авторская рубрика. Ответы проверяются на сервере.
                Возвращайся к заданиям, пока время не истекло.
              </p>
              <p>
                {attempt.policy?.notice ||
                  "Документация разрешена. Не используйте помощь ИИ или других людей."}
              </p>
              {needPractice && (
                <Notice>
                  Практика потребности компании. Глобальная категория не
                  меняется; контакты не открываются.
                </Notice>
              )}
              {kind === "demo" && (
                <Notice>
                  Демонстрационная попытка не присваивает категорию.
                </Notice>
              )}
            </section>
          </aside>
        </div>
      </section>
      {confirm && (
        <Modal
          title={needPractice ? "Завершить практику?" : "Завершить экзамен?"}
          description={
            needPractice
              ? "После отправки изменить ответы нельзя. Результат сохраняется отдельно от глобального грейда и не открывает контакты."
              : "После отправки изменить ответы нельзя. Результат сохраняется в истории проверки."
          }
          onClose={closeReview}
        >
          <div className="v-exam-review v-dialog-content">
            <Notice>
              Перед отправкой сервер проверяет только заполнение, формат и
              лимиты. Эта проверка не оценивает правильность ответов и не
              показывает баллы.
            </Notice>
            {reviewing && (
              <Loading label="Сохраняем черновик и проверяем формат ответов" />
            )}
            {review && (
              <>
                <Notice
                  tone={review.receipt.structural_ready ? "green" : "amber"}
                >
                  С ответом: {review.receipt.answered} из {review.receipt.total}
                  .
                  {review.receipt.structural_ready
                    ? " Формат допускает отправку; правильность ещё не проверена."
                    : " Проверь замечания перед отправкой."}
                </Notice>
                {review.receipt.issues.map((issue, ordinal) => {
                  const itemIndex = attempt.items.findIndex(
                    (q) => q.id === issue.item_id,
                  );
                  return (
                    <div
                      className="list-row v-review-item"
                      key={`${issue.item_id || "draft"}-${ordinal}`}
                    >
                      <div className="v-record-content">
                        <strong>
                          {itemIndex >= 0
                            ? `Задание ${itemIndex + 1}`
                            : "Черновик"}{" "}
                          ·{" "}
                          {issue.kind === "missing"
                            ? "нет ответа"
                            : issue.kind === "format"
                              ? "формат"
                              : "лимит"}
                        </strong>
                        <small className="v-record-meta">{issue.detail}</small>
                      </div>
                      {itemIndex >= 0 && (
                        <Button
                          variant="secondary"
                          onClick={() => {
                            setIndex(itemIndex);
                            closeReview();
                          }}
                        >
                          Исправить
                        </Button>
                      )}
                    </div>
                  );
                })}
                {review.receipt.issues.some(
                  (issue) => issue.kind === "missing",
                ) &&
                  !review.receipt.issues.some(
                    (issue) => issue.kind !== "missing",
                  ) && (
                    <label className="option top-gap v-answer-option">
                      <input
                        type="checkbox"
                        checked={allowMissing}
                        disabled={submitting}
                        onChange={(e) => setAllowMissing(e.target.checked)}
                      />
                      <span>
                        Сдать с пропущенными ответами. Пропуски будут учтены при
                        итоговой оценке, изменить ответы после сдачи нельзя.
                      </span>
                    </label>
                  )}
                <p className="safe-data-note">
                  Проверен формат черновика. Правильность ответов и итоговая
                  оценка определяются только после сдачи.
                </p>
              </>
            )}
            {reviewError !== undefined && (
              <div className="top-gap">
                <ErrorBox
                  error={reviewError}
                  retry={
                    !submitting && !reviewing
                      ? () =>
                          void (reviewSubmissionAllowed(review, allowMissing)
                            ? submit()
                            : beginReview())
                      : undefined
                  }
                />
              </div>
            )}
            <div className="modal-actions v-review-actions">
              <Button
                variant="secondary"
                onClick={closeReview}
                disabled={reviewing || submitting}
              >
                Вернуться к заданиям
              </Button>
              <Button
                busy={submitting}
                disabled={
                  reviewing || !reviewSubmissionAllowed(review, allowMissing)
                }
                onClick={() => void submit()}
              >
                Отправить на проверку <ArrowRight size={15} />
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </main>
  );
}
function AnswerEditor({
  item,
  value,
  onChange,
  disabled,
}: {
  item: Dict;
  value: unknown;
  onChange: (v: unknown) => void;
  disabled: boolean;
}) {
  if (
    ["single_choice", "multiple_choice", "choice", "multi_choice"].includes(
      item.type,
    )
  ) {
    const multi = ["multiple_choice", "multi_choice"].includes(item.type);
    return (
      <div
        className="v-answer-options"
        role="group"
        aria-label="Варианты ответа"
      >
        <p className="v-answer-hint">
          {multi
            ? "Можно выбрать несколько вариантов."
            : "Выбери один вариант."}
        </p>
        {(item.options || []).map((o: Dict) => {
          const selected = multi
            ? Array.isArray(value) && value.includes(o.id)
            : value === o.id;
          return (
            <label
              key={o.id}
              className={`option v-answer-option ${selected ? "selected" : ""}`}
            >
              <input
                type={multi ? "checkbox" : "radio"}
                name={item.id}
                value={o.id}
                checked={!!selected}
                disabled={disabled}
                onChange={() =>
                  onChange(
                    multi
                      ? selected
                        ? (value as string[]).filter((v) => v !== o.id)
                        : [...(Array.isArray(value) ? value : []), o.id]
                      : o.id,
                  )
                }
              />
              <span>{o.label}</span>
            </label>
          );
        })}
      </div>
    );
  }
  if (item.type === "number")
    return (
      <label className="field v-answer-field">
        <span>Числовой ответ</span>
        <input
          value={String(value ?? "")}
          onChange={(e) => onChange(e.target.value)}
          inputMode="decimal"
          disabled={disabled}
          placeholder="Введи число"
        />
      </label>
    );
  return (
    <label className="field v-answer-field">
      <span>
        {item.type === "sql"
          ? "SQL-запрос"
          : item.type === "json"
            ? "Структурированный ответ (JSON)"
            : "Твой ответ"}
      </span>
      <textarea
        className={
          ["sql", "json", "code"].includes(item.type)
            ? "code-input v-code-editor"
            : ""
        }
        spellCheck={false}
        disabled={disabled}
        value={
          typeof value === "object"
            ? JSON.stringify(value, null, 2)
            : String(value ?? "")
        }
        onChange={(e) => onChange(e.target.value)}
        placeholder={
          item.starter_code ||
          (item.type === "json"
            ? "Формат JSON указан в условии"
            : "Введи ответ")
        }
        aria-label={item.type === "sql" ? "Редактор SQL" : "Поле ответа"}
      />
      {item.public_cases && Object.keys(item.public_cases).length > 0 && (
        <details className="top-gap">
          <summary>Исходные данные и публичные примеры</summary>
          <pre className="code-input code-example">
            {JSON.stringify(item.public_cases, null, 2)}
          </pre>
        </details>
      )}
    </label>
  );
}
function ExamResult({ attempt }: { attempt: Attempt }) {
  const r = attempt.result || {};
  const kind = assessmentKind(attempt);
  const practice = kind === "need_practice";
  const certifiesGrade = hasGradeConfirmation(attempt);
  const competencies = Array.isArray(r.competencies)
    ? r.competencies
    : Object.entries(r.competencies || {}).map(([k, v]) =>
        typeof v === "object"
          ? {
              competency: k,
              label: attempt.items.find((q) => q.competency === k)
                ?.competency_label,
              ...(v as Dict),
            }
          : {
              competency: k,
              label: attempt.items.find((q) => q.competency === k)
                ?.competency_label,
              score: v,
            },
      );
  return (
    <main className="exam-layout v-exam">
      <ExamSidebar />
      <section className="exam-surface v-exam-surface">
        <header className="exam-header v-exam-header">
          <span className="exam-breadcrumb">
            {practice ? "Практика" : "Проверка"} / Результат
          </span>
          <Link
            className="button ghost exam-mobile-home"
            href="/workspace/passport"
          >
            <FileText size={15} /> Паспорт
          </Link>
          <Link className="button secondary" href="/workspace/overview">
            <Home size={15} /> В кабинет
          </Link>
        </header>
        <div className="exam-result linear-detail-layout v-detail-layout v-exam-result">
          <div className="linear-detail-main linear-document v-exam-main">
            <section
              className="v-result-summary"
              aria-labelledby="exam-result-title"
            >
              <Badge tone={r.passed ? "green" : "amber"}>
                {practice
                  ? r.passed
                    ? "Практика выполнена"
                    : "Практика не пройдена"
                  : kind === "demo"
                    ? "Демонстрация завершена"
                    : certifiesGrade
                      ? "Уровень подтверждён"
                      : "Пока не подтверждён"}
              </Badge>
              <h1 id="exam-result-title">
                {practice
                  ? "Наблюдение для этой команды сохранено"
                  : kind === "demo"
                    ? "Демонстрационный результат"
                    : certifiesGrade
                      ? `${specName(attempt.specialization)} · ${gradeName(r.confirmed_grade || attempt.grade)}`
                      : "Выбранный уровень пока не подтверждён"}
              </h1>
              <p>
                {practice
                  ? `Результат относится к ограниченной практике по потребности компании. Глобальная категория ${r.global_confirmed_grade ? `(${gradeName(r.global_confirmed_grade)})` : ""} не изменилась. Контакты не открыты этой попыткой.`
                  : kind === "demo"
                    ? "Эта попытка не присвоила грейд и не добавила подтверждённые компетенции."
                    : certifiesGrade
                      ? "Проверенные компетенции добавлены в паспорт. Включи публикацию, чтобы команды могли найти тебя."
                      : "Эта попытка не подтвердила выбранный уровень. Прежняя категория сохранена; можно подготовиться или добровольно выбрать другой уровень."}
              </p>
              <dl className="linear-properties v-property-list">
                <div className="linear-property-row v-property-row">
                  <dt>Результат</dt>
                  <dd>
                    {typeof r.score === "number"
                      ? `${Math.round(r.score)} / 100`
                      : "Баллы не сохранены"}
                  </dd>
                </div>
                <div className="linear-property-row v-property-row">
                  <dt>Маршрут</dt>
                  <dd>
                    {specName(attempt.specialization)} ·{" "}
                    {gradeName(attempt.grade)}
                  </dd>
                </div>
                <div className="linear-property-row v-property-row">
                  <dt>Источник</dt>
                  <dd>
                    {practice
                      ? "Практика компании"
                      : kind === "demo"
                        ? "Демонстрационная попытка"
                        : "Формальный экзамен"}
                  </dd>
                </div>
                <div className="linear-property-row v-property-row">
                  <dt>Дата</dt>
                  <dd>{date(attempt.started_at)}</dd>
                </div>
              </dl>
              <div className="result-actions v-form-actions">
                <Link
                  className="button primary"
                  href={
                    practice || kind === "demo"
                      ? "/workspace/practice"
                      : certifiesGrade
                        ? "/workspace/passport"
                        : "/workspace/assessment"
                  }
                >
                  {practice || kind === "demo"
                    ? "Вернуться к практике"
                    : certifiesGrade
                      ? "Открыть паспорт"
                      : "Выбрать следующий шаг"}
                  <ArrowRight size={15} />
                </Link>
                <Link className="button secondary" href="/workspace/history">
                  История результатов
                </Link>
              </div>
            </section>
            <section className="linear-section">
              <div className="panel-header">
                <h3>Разбор компетенций</h3>
                <ShieldCheck size={17} className="muted" />
              </div>
              <div className="linear-record-list v-record-list">
                {competencies.map((c: Dict, i: number) => (
                  <div
                    className="linear-record-row v-record v-record-competency v-result-competency"
                    key={c.competency || i}
                  >
                    <span className="v-record-content">
                      {competencyLabel(
                        c.label || c.competency_label || c.competency,
                      )}
                    </span>
                    <div className="v-record-score">
                      <Badge>
                        {typeof c.score === "number"
                          ? `${Math.round(c.score)} / 100`
                          : "Не измерено"}
                      </Badge>
                    </div>
                  </div>
                ))}
              </div>
              {!competencies.length && (
                <Empty
                  title="Подробный разбор не сохранён"
                  text="В этой записи нет отдельных баллов по компетенциям. Общий результат показан выше."
                />
              )}
              <hr />
              <div className="row between">
                <span className="muted">Практические действия</span>
                <Badge tone={r.practice_score >= 60 ? "green" : "amber"}>
                  {typeof r.practice_score === "number"
                    ? `${Math.round(r.practice_score)} / 100`
                    : "Не измерено"}
                </Badge>
              </div>
            </section>
          </div>
          <aside className="linear-column v-inspector">
            <section className="panel linear-document">
              <h3>Что означает результат</h3>
              <Notice tone="amber">
                Начальная экспертная рубрика. Человеческий пилот и
                психометрическая калибровка ещё не измерены.
              </Notice>
              {practice && (
                <Notice>
                  Источник: практика по потребности компании. Это отдельное
                  наблюдение; оно не становится глобальным экзаменом или
                  подтверждением всего заявленного стека.
                </Notice>
              )}
              <ul className="feedback-list v-feedback-list">
                {(Array.isArray(r.feedback) ? r.feedback : [r.feedback])
                  .filter(Boolean)
                  .map((f: unknown, i: number) => {
                    if (typeof f === "string") return <li key={i}>{f}</li>;
                    const entry = f as Dict;
                    const ordinal =
                      attempt.items.findIndex((q) => q.id === entry.item_id) +
                      1;
                    return (
                      <li key={i}>
                        {ordinal > 0 && <strong>Задание {ordinal}. </strong>}
                        {typeof entry.message === "string"
                          ? entry.message
                          : "Проверка завершена."}
                        {typeof entry.earned_score === "number" &&
                          typeof entry.max_score === "number" && (
                            <span className="muted">
                              {" "}
                              {entry.earned_score} из {entry.max_score} баллов.
                            </span>
                          )}
                      </li>
                    );
                  })}
              </ul>
              {!(Array.isArray(r.feedback) ? r.feedback : [r.feedback]).filter(
                Boolean,
              ).length && (
                <p className="v-result-feedback-empty">
                  В этой записи нет отдельных комментариев к заданиям.
                </p>
              )}
              <p>
                {practice
                  ? "Практика по потребности:"
                  : kind === "demo"
                    ? "Демонстрационная попытка:"
                    : "Экзамен:"}{" "}
                {date(attempt.started_at)}. Результат относится к выбранному
                маршруту и проверенным действиям. Он не подтверждает
                автоматически весь заявленный стек или опыт руководства.
              </p>
              {kind === "global_category" && r.next_eligible_at && (
                <p>Следующее изменение грейда: {date(r.next_eligible_at)}.</p>
              )}
            </section>
          </aside>
        </div>
      </section>
    </main>
  );
}

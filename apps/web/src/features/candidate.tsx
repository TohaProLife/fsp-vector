"use client";
import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Upload,
  Download,
  ShieldCheck,
  Link2,
  Unlink,
  Code2,
  Monitor,
  FlaskConical,
  Database,
  Workflow,
  LockKeyhole,
  Check,
  ArrowRight,
  FileText,
  ChevronRight,
  Eye,
  History as HistoryIcon,
  Info,
} from "lucide-react";
import {
  api,
  post,
  patch,
  Dict,
  Profile,
  items,
  date,
  specName,
  gradeName,
  evidenceSynthetic,
  evidenceLabel,
  evidenceScore,
  evidenceVerified,
  scopeText,
} from "@/lib/api";
import { useResource } from "@/lib/hooks";
import { fspProvenance } from "@/lib/fsp-provenance";
import { competencyLabel } from "@/lib/competency-label";
import {
  assessmentKind,
  assessmentStatus,
  availabilityState,
} from "@/lib/assessment-scope";
import {
  type AssessmentRoute,
  routeContexts,
  routeDefaults,
  validateRoute,
} from "@/lib/assessment-route";
import {
  Button,
  Field,
  PageTitle,
  Loading,
  ErrorBox,
  Notice,
  Empty,
  Tag,
  Badge,
  Avatar,
  Modal,
} from "@/components/ui";
import type { WorkspaceContext } from "@/components/workspace";
const formats = [
  ["remote", "Удалённо"],
  ["hybrid", "Гибрид"],
  ["office", "В офисе"],
  ["any", "Любой формат"],
];
const split = (s: unknown) =>
  String(s || "")
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean);
const gradeOptions = ["intern", "junior", "middle", "senior"];
function syntheticEvidence(e: Dict) {
  return evidenceSynthetic(e);
}
function passportEvidenceLabel(e: Dict) {
  return evidenceLabel(e);
}
export function passportCategoryProvenance(p: Profile, evidence: Dict[]) {
  if (!p.confirmed_grade)
    return { label: "До подтверждения", tone: "neutral" as const };
  const category = p.confirmed_categories?.[p.specialization];
  if (category && syntheticEvidence(category))
    return { label: "Синтетический пример", tone: "amber" as const };
  const categoryAttempt =
    category?.grade === p.confirmed_grade &&
    typeof category?.attempt_id === "string" &&
    category.attempt_id.length > 0;
  const matchingEvidence = evidence.some(
    (e) =>
      !syntheticEvidence(e) &&
      e.is_demo !== true &&
      evidenceVerified(e) &&
      typeof e.attempt_id === "string" &&
      e.attempt_id.length > 0 &&
      e.scope?.specialization === p.specialization &&
      e.scope?.grade === p.confirmed_grade &&
      e.scope?.global_grade !== false &&
      !e.scope?.company_id,
  );
  if (categoryAttempt || matchingEvidence)
    return { label: "Подтверждена экзаменом", tone: "green" as const };
  return !category && p.source === "synthetic_fixture"
    ? { label: "Синтетический пример", tone: "amber" as const }
    : { label: "Источник категории не указан", tone: "neutral" as const };
}
export function ProfileEditor(ctx: WorkspaceContext) {
  const {
    data: profile,
    error,
    loading,
    reload,
  } = useResource<Profile>("/candidate/profile");
  const [busy, setBusy] = useState(false);
  const [mutationError, setMutationError] = useState<unknown>();
  const [importData, setImportData] = useState<Dict | null>(null);
  const [importing, setImporting] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [draftVersion, setDraftVersion] = useState(0);
  if (loading)
    return (
      <>
        <PageTitle title="Мой профиль" />
        <Loading label="Загружаем сохранённый профиль" />
      </>
    );
  if (error !== undefined)
    return (
      <>
        <PageTitle title="Мой профиль" />
        <ErrorBox error={error} retry={() => void reload()} />
      </>
    );
  if (!profile)
    return (
      <>
        <PageTitle title="Мой профиль" />
        <Empty
          title="Профиль не получен"
          text="Обнови страницу, чтобы повторно загрузить сохранённые данные."
          action={
            <Button variant="secondary" onClick={() => void reload()}>
              Обновить профиль
            </Button>
          }
        />
      </>
    );
  const imported =
    importData?.draft ||
    importData?.profile ||
    importData?.extracted ||
    importData ||
    {};
  const merged = { ...profile, ...imported };
  const preferences = { ...profile.preferences, ...imported.preferences };
  const submit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setBusy(true);
    setMutationError(undefined);
    const f = new FormData(e.currentTarget);
    try {
      const salaryFrom = String(f.get("salary_from") ?? "").trim();
      const salaryTo = String(f.get("salary_to") ?? "").trim();
      if (Boolean(salaryFrom) !== Boolean(salaryTo))
        throw new Error(
          "Укажите обе границы зарплаты или оставьте оба поля пустыми.",
        );
      const low = Number(salaryFrom);
      const high = Number(salaryTo);
      if (
        salaryFrom &&
        (!Number.isSafeInteger(low) ||
          !Number.isSafeInteger(high) ||
          low <= 0 ||
          high < low ||
          high > 10000000)
      )
        throw new Error(
          "Зарплата: укажите целые суммы от 1 до 10 000 000 ₽; верхняя граница не меньше нижней.",
        );
      const salary = salaryFrom ? { salary_from: low, salary_to: high } : {};
      await patch("/candidate/profile", {
        name: f.get("name"),
        title: f.get("title"),
        bio: f.get("bio"),
        city: f.get("city"),
        skills: split(f.get("skills")),
        contacts: {
          phone: f.get("phone"),
          telegram: f.get("telegram"),
        },
        preferences: {
          ...salary,
          work_format: f.get("work_format"),
          employment: f.get("employment"),
        },
      });
      ctx.notify("Профиль сохранён");
      setImportData(null);
      await reload();
    } catch (e) {
      setMutationError(e);
    } finally {
      setBusy(false);
    }
  };
  const importFile = async () => {
    if (!file) return;
    if (file.size > 3 * 1024 * 1024) {
      setMutationError(new Error("PDF не должен превышать 3 МБ."));
      return;
    }
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setMutationError(new Error("Выбери PDF-файл."));
      return;
    }
    setImporting(true);
    setMutationError(undefined);
    try {
      const f = new FormData();
      f.set("file", file);
      setImportData(
        await api("/candidate/resume-import", { method: "POST", body: f }),
      );
      setDraftVersion((v) => v + 1);
      ctx.notify("Резюме разобрано. Проверь поля перед сохранением.");
    } catch (e) {
      setMutationError(e);
    } finally {
      setImporting(false);
    }
  };
  return (
    <>
      <PageTitle
        title="Мой профиль"
        description="Опиши опыт и условия. Подтверждённые навыки хранятся отдельно в паспорте."
        action={
          <a
            className="button secondary"
            href="/api/v1/candidate/profile.pdf"
            target="_blank"
            rel="noreferrer"
          >
            <Download size={15} /> Скачать PDF
          </a>
        }
      />
      <div className="linear-detail-layout v-detail-layout">
        <div className="linear-detail-main linear-settings v-detail-main v-profile-form">
          <div className="panel-header">
            <h2>Опыт и предпочтения</h2>
            <Badge>Заявлено тобой</Badge>
          </div>
          {importData && (
            <Notice>
              Поля заполнены из резюме. Это черновик: проверь значения и сохрани
              профиль.
            </Notice>
          )}
          <form
            key={draftVersion}
            onSubmit={submit}
            className="form-stack top-gap v-profile-fields"
          >
            <section
              className="v-form-section"
              aria-labelledby="profile-experience-heading"
            >
              <div className="v-section-heading">
                <h3 id="profile-experience-heading">
                  Профессиональный профиль
                </h3>
                <p>
                  Расскажи, чем занимаешься и какой опыт хочешь показать
                  командам.
                </p>
              </div>
              <div className="form-grid v-form-grid">
                <Field label="Имя и фамилия">
                  <input
                    name="name"
                    defaultValue={merged.name || ctx.me.name}
                    required
                    maxLength={100}
                  />
                </Field>
                <Field label="Город">
                  <input
                    name="city"
                    defaultValue={merged.city || ""}
                    placeholder="Москва"
                    maxLength={100}
                  />
                </Field>
                <Field label="Профессиональный заголовок">
                  <input
                    name="title"
                    defaultValue={merged.title || ""}
                    placeholder="Backend-разработчик"
                    maxLength={160}
                  />
                </Field>
                <Field
                  label="Навыки"
                  hint="Через запятую. Эти навыки останутся заявленными до проверки."
                >
                  <input
                    name="skills"
                    defaultValue={(merged.skills || []).join(", ")}
                    placeholder="Python, PostgreSQL, REST API"
                  />
                </Field>
                <div className="span-two">
                  <Field label="О себе и опыте">
                    <textarea
                      name="bio"
                      defaultValue={merged.bio || ""}
                      placeholder="Над какими задачами работал? Что хочешь делать дальше?"
                      maxLength={6000}
                    />
                  </Field>
                </div>
              </div>
            </section>
            <section
              className="v-form-section"
              aria-labelledby="profile-preferences-heading"
            >
              <div className="v-section-heading">
                <h3 id="profile-preferences-heading">Условия работы</h3>
                <p>Эти предпочтения помогают подобрать подходящие вакансии.</p>
              </div>
              <div className="form-grid v-form-grid">
                <Field
                  label="Зарплата от, ₽ в месяц"
                  hint="Необязательно. Укажите обе границы или оставьте их пустыми."
                >
                  <input
                    name="salary_from"
                    type="number"
                    min={1}
                    max={10000000}
                    defaultValue={preferences.salary_from ?? ""}
                  />
                </Field>
                <Field label="Зарплата до, ₽ в месяц">
                  <input
                    name="salary_to"
                    type="number"
                    min={1}
                    max={10000000}
                    defaultValue={preferences.salary_to ?? ""}
                  />
                </Field>
                <Field label="Формат работы">
                  <select
                    name="work_format"
                    defaultValue={preferences.work_format || "remote"}
                  >
                    {formats.map(([v, l]) => (
                      <option key={v} value={v}>
                        {l}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Занятость">
                  <select
                    name="employment"
                    defaultValue={preferences.employment || "full_time"}
                  >
                    <option value="full_time">Полная</option>
                    <option value="part_time">Частичная</option>
                    <option value="project">Проектная</option>
                  </select>
                </Field>
              </div>
            </section>
            <section
              className="v-form-section"
              aria-labelledby="profile-contacts-heading"
            >
              <div className="v-section-heading">
                <h3 id="profile-contacts-heading">Контакты</h3>
              </div>
              <Notice>
                Эти поля скрыты от компаний до принятия приглашения или отклика.
                Публикация профиля не открывает контакты.
              </Notice>
              <div className="form-grid v-form-grid">
                <Field
                  label="Подтверждённый email"
                  hint="Адрес связан с аккаунтом и защищён от изменения через резюме."
                >
                  <input
                    name="contact_email"
                    type="email"
                    defaultValue={profile.contacts?.email || ctx.me.email}
                    readOnly
                  />
                </Field>
                <Field label="Телефон">
                  <input
                    name="phone"
                    type="tel"
                    defaultValue={profile.contacts?.phone || ""}
                    placeholder="+7 …"
                  />
                </Field>
                <Field label="Telegram">
                  <input
                    name="telegram"
                    defaultValue={profile.contacts?.telegram || ""}
                    placeholder="@username"
                  />
                </Field>
              </div>
            </section>
            {mutationError !== undefined && <ErrorBox error={mutationError} />}
            <div className="v-form-actions">
              <Button busy={busy} type="submit">
                Сохранить профиль <Check size={15} />
              </Button>
            </div>
          </form>
        </div>
        <aside className="linear-column v-inspector">
          <div className="panel">
            <div className="panel-header">
              <h2>Импорт резюме</h2>
              <FileText size={17} className="muted" />
            </div>
            <p>
              Загрузите PDF, чтобы заполнить черновик профиля. Проверьте
              распознанные данные перед сохранением.
            </p>
            <div className="dropzone">
              <Upload size={25} />
              <strong>Резюме в PDF</strong>
              <small>Текстовый PDF. Скан может не распознаться.</small>
              <input
                type="file"
                accept="application/pdf,.pdf"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
                aria-label="Выбрать резюме PDF"
              />
              <Button
                variant="secondary"
                busy={importing}
                disabled={!file}
                onClick={() => void importFile()}
              >
                Импортировать
              </Button>
            </div>
            {importData?.warnings?.length > 0 && (
              <ul className="feedback-list v-feedback-list">
                {importData?.warnings.map((w: string) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            )}
          </div>
          <div className="panel">
            <div className="panel-header">
              <h2>Что увидит команда</h2>
              <Eye size={16} className="muted" />
            </div>
            <div className="fsp-row">
              <Avatar name={profile.alias} />
              <div>
                <strong>{profile.alias}</strong>
                <small>
                  {specName(profile.specialization)} ·{" "}
                  {gradeName(profile.confirmed_grade)}
                </small>
              </div>
            </div>
            <p className="safe-data-note">
              <LockKeyhole size={13} />
              Безопасный профиль содержит псевдоним, категорию, навыки и
              условия. Имя и контакты доступны только разрешённой компании.
            </p>
            <Link className="link-action" href="/workspace/privacy">
              Управлять публикацией <ArrowRight size={14} />
            </Link>
          </div>
        </aside>
      </div>
    </>
  );
}
export function Passport(ctx: WorkspaceContext) {
  const { data, error, loading, reload } = useResource<Dict>(
    "/candidate/passport",
  );
  const history = useResource<Dict>("/candidate/history");
  const [tab, setTab] = useState("overview");
  const [selectedEvidence, setSelectedEvidence] = useState<string | null>(null);
  const [linking, setLinking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [mutationError, setMutationError] = useState<unknown>();
  if (loading)
    return (
      <>
        <PageTitle title="Паспорт компетенций" />
        <Loading label="Загружаем паспорт и источники подтверждений" />
      </>
    );
  if (error !== undefined)
    return (
      <>
        <PageTitle title="Паспорт компетенций" />
        <ErrorBox error={error} retry={() => void reload()} />
      </>
    );
  if (!data)
    return (
      <>
        <PageTitle title="Паспорт компетенций" />
        <Empty
          title="Паспорт не получен"
          text="Обнови страницу, чтобы повторно загрузить сохранённые подтверждения."
          action={
            <Button variant="secondary" onClick={() => void reload()}>
              Обновить паспорт
            </Button>
          }
        />
      </>
    );
  const p = (data.profile || data) as Profile;
  const evidence = data.evidence || p.evidence || [];
  const fsp = data.fsp || p.fsp || {};
  const confirmed = p.confirmed_grade || data.confirmed_grade;
  const categoryProvenance = passportCategoryProvenance(
    { ...p, confirmed_grade: confirmed },
    evidence,
  );
  const attempts = items(history.data);
  const activeGrants = (p.contact_grants || []).filter(
    (g: Dict) => g.active !== false && !g.revoked_at,
  );
  const currentEvidence = evidence.find(
    (e: Dict, i: number) => String(e.id || i) === selectedEvidence,
  );
  const evidenceSources = [
    ...new Set(evidence.map((e: Dict) => passportEvidenceLabel(e))),
  ];
  const link = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setMutationError(undefined);
    try {
      await post("/candidate/fsp/link", {
        fsp_id: f.get("fsp_id"),
        proof_code: f.get("proof_code"),
      });
      setLinking(false);
      ctx.notify("Демонстрационная запись ФСП связана");
      await reload();
    } catch (e) {
      setMutationError(e);
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <PageTitle
        title="Паспорт компетенций"
        action={
          <a
            className="button secondary"
            href="/api/v1/candidate/profile.pdf"
            target="_blank"
            rel="noreferrer"
          >
            <Download size={15} /> Экспорт PDF
          </a>
        }
      />
      <div
        className="linear-pill-tabs v-view-tabs"
        role="group"
        aria-label="Раздел паспорта"
      >
        {[
          ["overview", "Обзор"],
          ["evidence", "Свидетельства"],
          ["history", "История"],
        ].map(([value, label]) => (
          <button
            key={value}
            className={tab === value ? "active" : ""}
            aria-pressed={tab === value}
            onClick={() => setTab(value)}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="linear-detail-layout v-detail-layout">
        <div className="linear-detail-main v-detail-main">
          <div className="linear-identity v-passport-identity">
            <Avatar name={p.name || ctx.me.name} />
            <div className="v-identity-copy">
              <h2>{p.name || ctx.me.name}</h2>
              <p>
                {specName(p.specialization)} · {gradeName(confirmed)}
              </p>
              <div className="v-identity-status">
                <Badge tone={categoryProvenance.tone}>
                  {categoryProvenance.label}
                </Badge>
                <span>
                  {p.category
                    ? `${specName(p.specialization)} · ${gradeName(confirmed)}`
                    : "Категория не присвоена"}
                </span>
              </div>
            </div>
          </div>
          <dl className="linear-properties v-property-list">
            <div className="linear-property-row v-property-row">
              <dt>Материалы</dt>
              <dd>
                <Link className="link-action" href="/workspace/profile">
                  Редактировать профиль
                </Link>
              </dd>
            </div>
            <div className="linear-property-row v-property-row">
              <dt>Контакты</dt>
              <dd>
                <LockKeyhole size={14} />
                <span>
                  {activeGrants.length
                    ? `Доступ для компаний: ${activeGrants.length}`
                    : "Закрыты для компаний"}
                </span>
                <Link href="/workspace/privacy" className="link-action">
                  Управлять доступом
                </Link>
              </dd>
            </div>
          </dl>
          {tab === "overview" && (
            <section className="linear-section linear-document">
              <h3>Описание</h3>
              <p>
                {p.bio ||
                  "Добавь описание опыта в профиле. Оно останется самоописанием и не заменит проверку навыков."}
              </p>
              <h3>Заявленные навыки</h3>
              <div className="tags">
                {(p.skills || []).map((s) => (
                  <Tag key={s}>{s}</Tag>
                ))}
                {!p.skills?.length && (
                  <span className="muted">Навыки пока не указаны.</span>
                )}
              </div>
            </section>
          )}
          {tab !== "history" && (
            <section
              className="linear-section v-passport-evidence"
              aria-labelledby="passport-evidence-heading"
            >
              <div className="panel-header">
                <h3 id="passport-evidence-heading">Свидетельства</h3>
                <Badge>{evidence.length}</Badge>
              </div>
              {evidence.length ? (
                <div className="linear-record-list v-record-list">
                  {evidence.map((e: Dict, i: number) => (
                    <div
                      className="linear-record-row v-record v-record-evidence"
                      key={e.id || i}
                    >
                      <ShieldCheck size={18} className="muted v-record-icon" />
                      <div className="v-record-content">
                        <strong>
                          {competencyLabel(e.label || e.competency || e.skill)}
                        </strong>
                        <span className="v-record-source">
                          {passportEvidenceLabel(e)}
                        </span>
                        <small className="v-record-meta">
                          {date(
                            e.confirmed_at || e.created_at || e.verified_at,
                          )}
                          {e.scope ? ` · ${scopeText(e.scope)}` : ""}
                        </small>
                      </div>
                      <div className="v-record-score">
                        <Badge
                          tone={
                            syntheticEvidence(e) || e.is_demo === true
                              ? "amber"
                              : evidenceVerified(e)
                                ? "green"
                                : "purple"
                          }
                        >
                          {evidenceScore(e) !== null
                            ? `${Math.round(evidenceScore(e)!)} / 100`
                            : "Без отдельного балла"}
                        </Badge>
                      </div>
                      <div className="v-record-actions">
                        <Button
                          variant="ghost"
                          aria-controls="passport-evidence-details"
                          aria-expanded={String(e.id || i) === selectedEvidence}
                          onClick={() => setSelectedEvidence(String(e.id || i))}
                        >
                          Основания <ChevronRight size={14} />
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <Empty
                  icon="check"
                  title="Первое подтверждение впереди"
                  text="Выбери свой уровень и пройди экзамен. Проверенные компетенции появятся в этом разделе."
                  action={
                    <Link
                      href="/workspace/assessment"
                      className="button primary"
                    >
                      Выбрать экзамен
                    </Link>
                  }
                />
              )}
            </section>
          )}
          {tab === "history" && (
            <section className="linear-section">
              <div className="panel-header">
                <h3>История попыток</h3>
                <Button variant="ghost" onClick={() => void history.reload()}>
                  Обновить
                </Button>
              </div>
              {history.loading ? (
                <Loading label="Загружаем историю" />
              ) : history.error !== undefined ? (
                <ErrorBox
                  error={history.error}
                  retry={() => void history.reload()}
                />
              ) : attempts.length ? (
                <div className="linear-record-list v-record-list">
                  {attempts.map((a) => (
                    <div
                      className="linear-record-row v-record v-record-history"
                      key={a.id}
                    >
                      <HistoryIcon size={18} className="muted v-record-icon" />
                      <div className="v-record-content">
                        <strong>
                          {specName(a.specialization)} · {gradeName(a.grade)}
                        </strong>
                        <small className="v-record-meta">
                          {date(a.started_at || a.created_at)} ·{" "}
                          {assessmentKind(a) === "global_category"
                            ? "Экзамен"
                            : assessmentKind(a) === "need_practice"
                              ? "Практика компании"
                              : "Демонстрация"}
                        </small>
                      </div>
                      <div className="v-record-status">
                        <Badge>{assessmentStatus(a)}</Badge>
                      </div>
                      <div className="v-record-actions">
                        <Link
                          className="link-action"
                          href={`/assessment/${a.id}`}
                        >
                          {["active", "in_progress"].includes(a.status)
                            ? "Продолжить"
                            : "Подробнее"}
                          <ChevronRight size={14} />
                        </Link>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <Empty
                  title="Попыток пока нет"
                  text="История появится после начала первой проверки."
                />
              )}
              <Link className="link-action top-gap" href="/workspace/history">
                Вся история
                {typeof history.data?.total === "number"
                  ? ` · ${history.data.total} попыток`
                  : ""}{" "}
                <ChevronRight size={14} />
              </Link>
            </section>
          )}
          <section className="linear-section linear-document">
            <h3>Границы подтверждения</h3>
            <p>
              {categoryProvenance.label === "Синтетический пример" &&
                "Категория и помеченные свидетельства загружены из синтетического набора. Они не являются результатом пройденного человеком экзамена. "}
              {data.calibration_status === "pilot"
                ? "Результат получен по пилотной шкале."
                : "Пороги заданы в версии рубрики; человеческая калибровка не проводилась."}{" "}
              Экзамен подтверждает проверенные действия в конкретном контексте.
              Указанный в резюме стек не становится подтверждённым
              автоматически.
            </p>
          </section>
        </div>
        <aside className="linear-column v-inspector">
          <section className="panel linear-properties">
            <h3>Свойства</h3>
            <dl className="v-property-list">
              <div className="linear-property-row v-property-row">
                <dt>Направление</dt>
                <dd>{specName(p.specialization)}</dd>
              </div>
              <div className="linear-property-row v-property-row">
                <dt>Грейд</dt>
                <dd>{gradeName(confirmed)}</dd>
              </div>
              <div className="linear-property-row v-property-row">
                <dt>Основание</dt>
                <dd>{categoryProvenance.label}</dd>
              </div>
              <div className="linear-property-row v-property-row">
                <dt>Публикация</dt>
                <dd>{p.published ? "Без контактов" : "Приватный профиль"}</dd>
              </div>
              <div className="linear-property-row v-property-row">
                <dt>Владелец</dt>
                <dd>{p.name || ctx.me.name}</dd>
              </div>
              <div className="linear-property-row v-property-row">
                <dt>ID</dt>
                <dd>
                  <code>
                    {String(p.id || ctx.me.id)
                      .slice(0, 8)
                      .toUpperCase()}
                  </code>
                </dd>
              </div>
            </dl>
            <Link className="link-action" href="/workspace/privacy">
              Настроить видимость <ArrowRight size={14} />
            </Link>
          </section>
          <section
            className="panel"
            id="passport-evidence-details"
            role="region"
            aria-label="Основания свидетельства"
            aria-live="polite"
          >
            <h3>{currentEvidence ? "Основания свидетельства" : "Источники"}</h3>
            {currentEvidence ? (
              <div className="linear-document">
                <strong>
                  {competencyLabel(
                    currentEvidence.label ||
                      currentEvidence.competency ||
                      currentEvidence.skill,
                  )}
                </strong>
                <dl className="linear-properties v-property-list">
                  <div className="linear-property-row v-property-row">
                    <dt>Источник</dt>
                    <dd>{passportEvidenceLabel(currentEvidence)}</dd>
                  </div>
                  <div className="linear-property-row v-property-row">
                    <dt>Дата</dt>
                    <dd>
                      {date(
                        currentEvidence.confirmed_at ||
                          currentEvidence.created_at ||
                          currentEvidence.verified_at,
                      )}
                    </dd>
                  </div>
                  <div className="linear-property-row v-property-row">
                    <dt>Область</dt>
                    <dd>
                      {currentEvidence.scope
                        ? scopeText(currentEvidence.scope)
                        : "Указана в источнике"}
                    </dd>
                  </div>
                </dl>
                <p>
                  Свидетельство относится к этой компетенции и своему контексту.
                  Оно не подтверждает весь заявленный стек.
                </p>
                <Button
                  variant="ghost"
                  onClick={() => setSelectedEvidence(null)}
                >
                  Все источники
                </Button>
              </div>
            ) : (
              <div className="linear-source-list v-source-list">
                {evidenceSources.map((source) => (
                  <div
                    className="linear-record-row v-record v-source-item"
                    key={String(source)}
                  >
                    <ShieldCheck size={16} className="muted v-record-icon" />
                    <span className="v-record-content">{String(source)}</span>
                  </div>
                ))}
                <div className="linear-record-row v-record v-source-item">
                  <FileText size={16} className="muted v-record-icon" />
                  <span className="v-record-content">Заявлено кандидатом</span>
                </div>
                <div className="linear-record-row v-record v-source-item">
                  <Database size={16} className="muted v-record-icon" />
                  <span className="v-record-content">
                    ФСП: {fspLabel(fsp.status)}
                  </span>
                </div>
              </div>
            )}
          </section>
          <section className="panel">
            <div className="panel-header">
              <h3>Достижения ФСП</h3>
              <Database size={15} className="muted" />
            </div>
            <Badge
              tone={
                fsp.status === "sync_ok"
                  ? "green"
                  : fsp.status === "sync_failed"
                    ? "amber"
                    : "neutral"
              }
            >
              {fspLabel(fsp.status)}
            </Badge>
            <p className="top-gap">
              Участие в соревнованиях дополняет паспорт. Спортивные достижения
              не заменяют подтверждение ИТ-грейда.
            </p>
            {fsp.achievements?.length ? (
              fsp.achievements.map((a: Dict, i: number) => (
                <div
                  key={a.id || i}
                  className="fsp-achievement v-fsp-achievement"
                >
                  <Badge
                    tone={
                      fspProvenance({
                        ...fsp,
                        ...a,
                        is_demo: fsp.is_demo || a.is_demo,
                      }).tone
                    }
                  >
                    {
                      fspProvenance({
                        ...fsp,
                        ...a,
                        is_demo: fsp.is_demo || a.is_demo,
                      }).label
                    }
                  </Badge>
                  <div className="top-gap v-record-content">
                    <strong>{a.event_name || a.title || a.name}</strong>
                    <p className="v-record-meta">
                      {a.discipline} ·{" "}
                      {a.place ? `${a.place} место` : "Участие"} ·{" "}
                      {date(a.event_date || a.date)}
                    </p>
                    <p className="v-record-meta">
                      {a.team_name
                        ? `Команда: ${a.team_name}`
                        : a.participation_type || "Индивидуальный результат"}
                    </p>
                  </div>
                </div>
              ))
            ) : (
              <div className="linear-record-row v-record v-source-item">
                <HistoryIcon size={18} className="muted v-record-icon" />
                <div className="v-record-content">
                  <strong>
                    {fsp.status === "linked_no_history"
                      ? "Запись связана, истории пока нет"
                      : "Твой опыт может быть здесь"}
                  </strong>
                  <small className="v-record-meta">
                    Без ФСП доступен полноценный путь найма
                  </small>
                </div>
              </div>
            )}
            <div className="top-gap">
              {[
                "verified_demo",
                "sync_ok",
                "linked_no_history",
                "sync_stale",
                "sync_failed",
              ].includes(fsp.status) ? (
                <Button
                  variant="secondary"
                  busy={busy}
                  onClick={async () => {
                    setBusy(true);
                    try {
                      await api("/candidate/fsp/link", { method: "DELETE" });
                      await reload();
                      ctx.notify("Связь с реестром удалена");
                    } catch (e) {
                      setMutationError(e);
                    } finally {
                      setBusy(false);
                    }
                  }}
                >
                  <Unlink size={14} /> Отвязать запись
                </Button>
              ) : (
                <Button variant="secondary" onClick={() => setLinking(true)}>
                  <Link2 size={14} /> Связать ФСП ID
                </Button>
              )}
            </div>
            {mutationError !== undefined && !linking && (
              <div className="top-gap">
                <ErrorBox error={mutationError} />
              </div>
            )}
            <p className="safe-data-note">
              <ShieldCheck size={13} />
              Сейчас доступен синтетический демореестр. Настоящий API ФСП ещё не
              подключён.
            </p>
          </section>
          <section className="panel">
            <div className="panel-header">
              <h3>Последние попытки</h3>
              <HistoryIcon size={15} className="muted" />
            </div>
            {history.loading ? (
              <Loading label="Загружаем попытки" />
            ) : history.error !== undefined ? (
              <ErrorBox
                error={history.error}
                retry={() => void history.reload()}
              />
            ) : attempts.length ? (
              attempts.slice(0, 3).map((a) => (
                <div
                  className="linear-record-row v-record v-record-preview"
                  key={a.id}
                >
                  <div className="v-record-content">
                    <strong>{specName(a.specialization)}</strong>
                    <small className="v-record-meta">
                      {date(a.started_at || a.created_at)}
                    </small>
                  </div>
                  <div className="v-record-actions">
                    <Link className="link-action" href={`/assessment/${a.id}`}>
                      {assessmentStatus(a)}
                    </Link>
                  </div>
                </div>
              ))
            ) : (
              <p className="muted">История пока пуста.</p>
            )}
            <Link className="link-action" href="/workspace/history">
              Вся история <ChevronRight size={14} />
            </Link>
          </section>
        </aside>
      </div>
      {linking && (
        <Modal
          title="Связать ФСП ID"
          description="Нужно подтвердить владение записью. Произвольный ID не даёт доступ к чужим достижениям."
          onClose={() => setLinking(false)}
        >
          <form onSubmit={link} className="form-stack">
            <Notice>
              Локальная демонстрация: используйте данные своей синтетической
              записи. Реальный реестр не подключён.
            </Notice>
            <Field label="ФСП ID">
              <input name="fsp_id" required placeholder="DEMO-…" />
            </Field>
            <Field label="Код подтверждения владения">
              <input
                name="proof_code"
                required
                autoComplete="one-time-code"
                placeholder="Код из демореестра"
              />
            </Field>
            {fsp.demo_identity && (
              <Notice tone="amber">
                Данные вашей демозаписи: {fsp.demo_identity.fsp_id} ·{" "}
                {fsp.demo_identity.proof_code}
              </Notice>
            )}
            {mutationError !== undefined && <ErrorBox error={mutationError} />}
            <Button type="submit" busy={busy}>
              Подтвердить связь
            </Button>
          </form>
        </Modal>
      )}
    </>
  );
}
function fspLabel(status: string) {
  return (
    (
      {
        not_linked: "Не связана",
        verified_demo: "Демозапись связана",
        linked_no_history: "Связана, без истории",
        sync_ok: "Связана",
        sync_stale: "Требуется обновление",
        sync_failed: "Источник недоступен",
        record_revoked: "Подтверждение отозвано",
        revoked: "Связь отозвана",
      } as Record<string, string>
    )[status] || "Не связана"
  );
}
export function Privacy(ctx: WorkspaceContext) {
  const profile = useResource<Profile>("/candidate/profile");
  const consents = useResource<Dict>("/candidate/consents");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [publishModal, setPublishModal] = useState(false);
  const [processingConfirm, setProcessingConfirm] = useState(false);
  const [grantConfirm, setGrantConfirm] = useState<Dict | null>(null);
  if (profile.loading || consents.loading)
    return (
      <>
        <PageTitle title="Приватность" />
        <Loading label="Загружаем действующие согласия и разрешения" />
      </>
    );
  if (profile.error !== undefined || consents.error !== undefined)
    return (
      <>
        <PageTitle title="Приватность" />
        <ErrorBox error={profile.error || consents.error} />
      </>
    );
  const p = profile.data;
  const grants = p?.contact_grants || [];
  const consentItems = items(consents.data);
  const processing =
    consents.data?.current?.processing ??
    consentItems.some((c) => c.purpose === "processing" && c.granted);
  const practiceNotifications =
    consents.data?.effective_practice_notifications ??
    consents.data?.current?.practice ??
    false;
  const changePracticeNotifications = async () => {
    setBusy(true);
    setError(undefined);
    try {
      const response = await post<Dict>("/candidate/consents", {
        purpose: "practice",
        granted: !practiceNotifications,
      });
      consents.setData(response);
      ctx.notify(
        practiceNotifications
          ? "Напоминания о практике отключены"
          : "Напоминания о практике включены",
      );
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };
  const changeProcessing = async () => {
    setBusy(true);
    setError(undefined);
    try {
      await post("/candidate/consents", {
        purpose: "processing",
        granted: !processing,
      });
      setProcessingConfirm(false);
      await consents.reload();
      ctx.refresh();
      ctx.notify(
        processing
          ? "Согласие на обработку отозвано"
          : "Согласие на обработку сохранено",
      );
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };
  const revokeGrant = async (id: string) => {
    setBusy(true);
    setError(undefined);
    try {
      await post(`/candidate/contact-grants/${id}/revoke`);
      setGrantConfirm(null);
      await consents.reload();
      await profile.reload();
      ctx.notify("Доступ компании отозван");
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };
  const publication = async (value: boolean) => {
    setBusy(true);
    setError(undefined);
    try {
      await post("/candidate/publication", {
        published: value,
        consent_publication: value,
      });
      await profile.reload();
      await consents.reload();
      setPublishModal(false);
      ctx.notify(
        value
          ? "Безопасный профиль опубликован"
          : "Профиль скрыт из новых подборок",
      );
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <PageTitle
        title="Приватность"
        description="Управляй публикацией и доступом каждой компании отдельно."
      />
      <div className="linear-settings">
        <section className="linear-section">
          <h2>Публикация и контакты</h2>
          <div className="panel">
            <div className="settings-row v-settings-row">
              <div>
                <h3>Публикация безопасного профиля</h3>
                <p>
                  Компаниям будут видны псевдоним, категория, навыки, допустимые
                  достижения и условия работы. Контакты останутся скрыты.
                </p>
              </div>
              <select
                value={p?.published ? "published" : "private"}
                aria-label="Публикация профиля"
                disabled={busy}
                onChange={(e) =>
                  e.target.value === "private"
                    ? void publication(false)
                    : setPublishModal(true)
                }
              >
                <option value="private">Приватный профиль</option>
                <option value="published">Без контактов</option>
              </select>
            </div>
            <div className="settings-row v-settings-row">
              <div>
                <h3>Доступ к контактам</h3>
                <p>
                  Разрешение действует только для конкретной компании после
                  принятого приглашения или отклика.
                </p>
              </div>
              <Badge>Адресные разрешения</Badge>
            </div>
            <div className="settings-row v-settings-row">
              <div>
                <h3>Напоминания о короткой практике</h3>
                <p>
                  Отдельное согласие на уведомления о задании недели. Решать
                  задачи можно и без напоминаний.
                </p>
              </div>
              <button
                className={`switch ${practiceNotifications ? "on" : ""}`}
                role="switch"
                aria-checked={practiceNotifications}
                aria-label="Напоминания о короткой практике"
                disabled={busy}
                onClick={() => void changePracticeNotifications()}
              />
            </div>
            {error !== undefined && <ErrorBox error={error} />}
          </div>
        </section>
        <section className="linear-section">
          <h2>Согласие на обработку данных</h2>
          <div className="panel">
            <div className="settings-row v-settings-row">
              <div>
                <h3>Текущее согласие</h3>
                <p>
                  Нужно для профиля, проверки навыков и работы приглашений.
                  Фиксируется отдельно от публикации.
                </p>
              </div>
              <Badge tone={processing ? "green" : "neutral"}>
                {processing ? "Действует" : "Не выдано"}
              </Badge>
            </div>
            <div className="settings-row v-settings-row">
              <div>
                <h3>{processing ? "Отзыв согласия" : "Разрешить обработку"}</h3>
                <p>
                  {processing
                    ? "Остановит профессиональные операции до нового согласия."
                    : "Возобновит работу платформы без восстановления прежних разрешений на контакты."}
                </p>
              </div>
              <Button
                variant={processing ? "danger" : "secondary"}
                busy={busy}
                onClick={() =>
                  processing
                    ? setProcessingConfirm(true)
                    : void changeProcessing()
                }
              >
                {processing ? "Отозвать согласие" : "Дать согласие"}
              </Button>
            </div>
          </div>
        </section>
        <div className="panel top-gap">
          <div className="panel-header">
            <h2>Компании с доступом к контактам</h2>
            <Badge>
              {
                grants.filter((g: Dict) => g.active !== false && !g.revoked_at)
                  .length
              }
            </Badge>
          </div>
          <Notice>
            Отзыв закрывает дальнейший доступ в платформе. Компания могла уже
            увидеть или сохранить контакты; такие копии технически нельзя
            удалить отсюда.
          </Notice>
          {grants.length ? (
            grants.map((g: Dict) => (
              <div className="settings-row v-settings-row" key={g.id}>
                <div>
                  <h3>{g.company_name || g.company?.name || "Компания"}</h3>
                  <p>
                    {g.source === "application"
                      ? "Отклик на вакансию"
                      : "Принятое приглашение"}{" "}
                    · {date(g.created_at)}{" "}
                    {g.revoked_at ? "· Доступ отозван" : ""}
                  </p>
                </div>
                {g.active !== false && !g.revoked_at ? (
                  <Button
                    variant="secondary"
                    busy={busy}
                    onClick={() => setGrantConfirm(g)}
                  >
                    Отозвать доступ
                  </Button>
                ) : (
                  <Badge>Отозван</Badge>
                )}
              </div>
            ))
          ) : (
            <Empty
              title="Доступ никому не открыт"
              text="Контакты станут доступны конкретной компании после принятия приглашения или отправки отклика."
              icon="check"
            />
          )}
        </div>
        {(p?.blocked_companies || []).length > 0 && (
          <div className="panel top-gap">
            <div className="panel-header">
              <h2>Заблокированные компании</h2>
              <Badge>{p?.blocked_companies.length}</Badge>
            </div>
            {p?.blocked_companies.map((c: Dict) => (
              <div
                className="settings-row v-settings-row"
                key={c.company_id || c.id}
              >
                <div>
                  <h3>{c.name}</h3>
                  <p>Новые приглашения закрыты · {date(c.created_at)}</p>
                </div>
                <Button
                  variant="secondary"
                  busy={busy}
                  onClick={async () => {
                    setBusy(true);
                    setError(undefined);
                    try {
                      await api(
                        `/candidate/companies/${c.company_id || c.id}/block`,
                        { method: "DELETE" },
                      );
                      await profile.reload();
                      ctx.notify(
                        "Компания разблокирована. Старые разрешения контактов не восстановлены.",
                      );
                    } catch (e) {
                      setError(e);
                    } finally {
                      setBusy(false);
                    }
                  }}
                >
                  Разблокировать
                </Button>
              </div>
            ))}
          </div>
        )}
        <section className="linear-section">
          <h2>Правила доступа</h2>
          <div className="panel">
            <div className="settings-row linear-settings-rule v-settings-row">
              <div>
                <h3>Публикация не отзывает выданные разрешения</h3>
                <p>
                  Скрытие профиля исключает его из новых подборок. Доступ каждой
                  компании отзывается отдельно.
                </p>
              </div>
              <Info size={17} className="muted" />
            </div>
            <div className="settings-row linear-settings-rule v-settings-row">
              <div>
                <h3>Разблокировка не восстанавливает доступ</h3>
                <p>
                  После разблокировки компании старые разрешения на контакты
                  остаются отозванными.
                </p>
              </div>
              <Info size={17} className="muted" />
            </div>
          </div>
        </section>
      </div>
      {processingConfirm && (
        <Modal
          title="Отозвать согласие на обработку?"
          description="Профиль будет скрыт, доступ компаний к контактам закроется. Профессиональные операции остановятся до нового согласия."
          onClose={() => setProcessingConfirm(false)}
        >
          <Notice tone="amber">
            Скопированные ранее компанией контакты технически нельзя удалить
            отсюда. Результаты не будут выдаваться за новые подтверждения.
          </Notice>
          {error !== undefined && (
            <div className="top-gap">
              <ErrorBox error={error} />
            </div>
          )}
          <div className="modal-actions v-form-actions">
            <Button
              variant="secondary"
              onClick={() => setProcessingConfirm(false)}
            >
              Оставить согласие
            </Button>
            <Button
              variant="danger"
              busy={busy}
              onClick={() => void changeProcessing()}
            >
              Отозвать согласие
            </Button>
          </div>
        </Modal>
      )}
      {grantConfirm && (
        <Modal
          title="Закрыть доступ компании?"
          description={`${grantConfirm.company_name || "Компания"} больше не сможет получать контакты через платформу.`}
          onClose={() => setGrantConfirm(null)}
        >
          <Notice tone="amber">
            Компания могла уже увидеть или скопировать данные. Такие копии
            нельзя забрать обратно через платформу.
          </Notice>
          {error !== undefined && (
            <div className="top-gap">
              <ErrorBox error={error} />
            </div>
          )}
          <div className="modal-actions v-form-actions">
            <Button variant="secondary" onClick={() => setGrantConfirm(null)}>
              Оставить доступ
            </Button>
            <Button
              variant="danger"
              busy={busy}
              onClick={() => void revokeGrant(grantConfirm.id)}
            >
              Отозвать доступ
            </Button>
          </div>
        </Modal>
      )}
      {publishModal && (
        <Modal
          title="Открыть профиль для команд?"
          description="Публикация помогает компаниям находить тебя по подтверждённым компетенциям."
          onClose={() => setPublishModal(false)}
        >
          <div className="form-stack">
            <Notice>
              Публикуется безопасная карточка. Имя, телефон, email и Telegram
              остаются закрыты.
            </Notice>
            <p>
              Нажимая «Дать согласие и опубликовать», ты даёшь отдельное
              согласие на публикацию указанных данных. Его можно отозвать в
              любой момент.
            </p>
            {error !== undefined && <ErrorBox error={error} />}
            <Button busy={busy} onClick={() => void publication(true)}>
              Дать согласие и опубликовать <Eye size={15} />
            </Button>
          </div>
        </Modal>
      )}
    </>
  );
}
export function AssessmentSetup(ctx: WorkspaceContext) {
  const router = useRouter();
  const catalog = useResource<Dict>("/assessments/catalog");
  const profile = useResource<Profile>("/candidate/profile");
  const [specialization, setSpecialization] = useState("backend");
  const availability = useResource<Dict>(
    `/assessments/availability?specialization=${encodeURIComponent(specialization)}`,
  );
  const [grade, setGrade] = useState("middle");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [step, setStep] = useState(1);
  const [stack, setStack] = useState("");
  const [industry, setIndustry] = useState("product");
  const [format, setFormat] = useState("remote");
  const initialized = useRef(false);
  useEffect(() => {
    if (initialized.current || !catalog.data || !profile.data) return;
    initialized.current = true;
    const p = profile.data;
    const routeId =
      p.survey?.specialization ||
      p.specialization ||
      catalog.data.specializations?.[0]?.id ||
      "backend";
    const route = catalog.data.specializations?.find(
      (s: Dict) => s.id === routeId,
    );
    setSpecialization(routeId);
    setGrade(p.survey?.grade || p.declared_grade || "middle");
    setStack(
      p.survey?.stack?.length
        ? p.survey.stack.join(", ")
        : routeDefaults(route).join(", "),
    );
    setIndustry(p.survey?.industry || "product");
    setFormat(p.survey?.work_format || p.preferences?.work_format || "remote");
  }, [catalog.data, profile.data]);
  if (catalog.loading || profile.loading)
    return (
      <>
        <PageTitle title="Твой маршрут проверки" />
        <Loading label="Загружаем маршруты проверки и текущий профиль" />
      </>
    );
  if (catalog.error !== undefined || profile.error !== undefined)
    return (
      <>
        <PageTitle title="Твой маршрут проверки" />
        <ErrorBox error={catalog.error || profile.error} />
      </>
    );
  const specs = catalog.data?.specializations || [];
  const grades =
    catalog.data?.grades ||
    gradeOptions.map((id) => ({ id, label: gradeName(id) }));
  const selected = specs.find((s: Dict) => s.id === specialization);
  const routeCheck = validateRoute(selected, grade, split(stack));
  const access = availabilityState(availability.data, specialization, grade);
  const ensureValidRoute = () => {
    if (!routeCheck.valid) {
      setError(new Error(routeCheck.message));
      return false;
    }
    return true;
  };
  const icons: Record<string, typeof Code2> = {
    backend: Code2,
    frontend: Monitor,
    qa: FlaskConical,
    devops: Workflow,
    data: Database,
    data_analytics: Database,
    security: ShieldCheck,
  };
  const saveSurvey = async () => {
    if (!ensureValidRoute()) return;
    setBusy(true);
    setError(undefined);
    try {
      await post("/candidate/survey", {
        industry,
        specialization,
        grade,
        stack: split(stack),
        work_format: format,
      });
      setStep(2);
      void availability.reload();
      ctx.notify("Маршрут сохранён");
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };
  const start = async () => {
    if (!ensureValidRoute()) return;
    setBusy(true);
    setError(undefined);
    try {
      const attempt = await post("/assessments/start", {
        specialization,
        grade,
        stack: split(stack),
        demo: false,
      });
      router.push(`/assessment/${attempt.id}`);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <PageTitle
        title="Твой маршрут проверки"
        description="Выбери уровень, который хочешь подтвердить. Неуспешная попытка не изменит прежнюю категорию."
      />
      <div className="linear-detail-layout v-detail-layout">
        <div className="linear-detail-main v-detail-main">
          <div
            className="progress-step v-assessment-stepper"
            role="group"
            aria-label={`Шаг ${step} из 2`}
          >
            <span className={step === 1 ? "current" : "done"}>
              {step > 1 ? <Check size={11} /> : "1"}
            </span>
            <strong className={step === 1 ? "current" : "done"}>
              Выбор маршрута
            </strong>
            <ChevronRight size={12} />
            <span className={step === 2 ? "current" : ""}>2</span>
            <strong className={step === 2 ? "current" : ""}>
              Перед экзаменом
            </strong>
          </div>
          {step === 1 ? (
            <div className="form-stack v-assessment-form">
              <h2>В чём твоя специализация?</h2>
              <div
                className="linear-record-list survey-tracks v-selection-list"
                role="group"
                aria-label="Выбор специализации"
              >
                {specs.map((s: Dict) => {
                  const Icon = icons[s.id] || Code2;
                  return (
                    <button
                      key={s.id}
                      className={`track-choice linear-record-row v-track-option ${specialization === s.id ? "active" : ""}`}
                      aria-pressed={specialization === s.id}
                      onClick={() => {
                        setSpecialization(s.id);
                        setStack(
                          routeDefaults(s as AssessmentRoute).join(", "),
                        );
                        setError(undefined);
                      }}
                    >
                      <Icon size={16} />
                      <strong>{s.label || specName(s.id)}</strong>
                    </button>
                  );
                })}
              </div>
              <Field label="Уровень для проверки" group>
                <div className="grade-choices v-grade-choices">
                  {grades.map((g: Dict) => (
                    <button
                      key={g.id}
                      className={grade === g.id ? "active" : ""}
                      aria-pressed={grade === g.id}
                      aria-label={g.label}
                      onClick={() => setGrade(g.id)}
                    >
                      {g.label}
                    </button>
                  ))}
                </div>
              </Field>
              <Field
                label="Стек"
                hint="Маршрут проверяет только поддерживаемые темы; указание технологии само по себе не подтверждает её."
              >
                <input
                  value={stack}
                  onChange={(e) => setStack(e.target.value)}
                  placeholder={routeDefaults(selected).join(", ")}
                />
              </Field>
              <div className="linear-section">
                <h3>Поддерживаемые контексты</h3>
                <div className="tags">
                  {routeContexts(selected).map((value) => (
                    <Tag key={value}>{value}</Tag>
                  ))}
                </div>
                {routeCheck.aliases.length > 0 && (
                  <p className="top-gap">
                    Синонимы проверяются в контексте:{" "}
                    {routeCheck.aliases.join(" · ")}. Текст ввода сохраняется.
                  </p>
                )}
                {routeCheck.unknown.length > 0 && (
                  <p className="top-gap">
                    Не поддерживается: {routeCheck.unknown.join(", ")}.
                  </p>
                )}
                <Button
                  variant="ghost"
                  className="top-gap"
                  onClick={() => {
                    setStack(routeDefaults(selected).join(", "));
                    setError(undefined);
                  }}
                >
                  Использовать рекомендованный контекст
                </Button>
              </div>
              <div className="form-grid v-form-grid">
                <Field label="Отраслевой контекст">
                  <select
                    value={industry}
                    onChange={(e) => setIndustry(e.target.value)}
                  >
                    <option value="product">Продуктовая разработка</option>
                    <option value="fintech">Финтех</option>
                    <option value="ecommerce">Электронная коммерция</option>
                    <option value="enterprise">Корпоративные системы</option>
                    <option value="public">Государственные сервисы</option>
                    <option value="any">Любой контекст</option>
                  </select>
                </Field>
                <Field label="Предпочтительный формат">
                  <select
                    value={format}
                    onChange={(e) => setFormat(e.target.value)}
                  >
                    {formats.map(([v, l]) => (
                      <option key={v} value={v}>
                        {l}
                      </option>
                    ))}
                  </select>
                </Field>
              </div>
              {error !== undefined && <ErrorBox error={error} />}
              <div className="v-form-actions">
                <Button busy={busy} onClick={() => void saveSurvey()}>
                  Сохранить маршрут <ArrowRight size={16} />
                </Button>
              </div>
            </div>
          ) : (
            <div className="assessment-intro v-assessment-plan">
              <Badge tone="purple">
                {specName(specialization)} · {gradeName(grade)}
              </Badge>
              <h2 className="top-gap">Покажем навыки в деле</h2>
              <p>
                Экзамен сочетает короткие вопросы, анализ ситуаций и безопасные
                практические задания. У вариантов общий стандарт, но разные
                условия.
              </p>
              <dl className="linear-properties v-property-list">
                <div className="linear-property-row v-property-row">
                  <dt>Задания</dt>
                  <dd>{catalog.data?.item_count || 12}</dd>
                </div>
                <div className="linear-property-row v-property-row">
                  <dt>Время</dt>
                  <dd>{catalog.data?.duration_minutes || 40} мин</dd>
                </div>
                <div className="linear-property-row v-property-row">
                  <dt>Ориентир</dt>
                  <dd>70 / 100 · с минимумами по компетенциям</dd>
                </div>
                <div className="linear-property-row v-property-row">
                  <dt>Рубрика</dt>
                  <dd>Начальная авторская</dd>
                </div>
              </dl>
              <Notice>
                Ответы сохраняются на сервере. При перезагрузке продолжишь ту же
                попытку. Время и решение об уровне определяет сервер.
              </Notice>
              <p className="top-gap">
                {catalog.data?.policy?.notice ||
                  "Можно пользоваться документацией. Не передавай задания другим людям и не используй помощь ИИ для ответа."}
              </p>
              <p className="muted">
                * Для успеха нужны также минимумы по компетенциям и практике.
                Пороги заданы в версии рубрики. После успешного изменения грейда
                действует период ограничения в 90 дней.
              </p>
              {availability.loading ? (
                <Loading label="Проверяем доступность попытки" />
              ) : availability.error !== undefined ? (
                <ErrorBox
                  error={availability.error}
                  retry={() => void availability.reload()}
                />
              ) : access.conflict ? (
                <Notice tone="amber">
                  Сначала заверши текущую{" "}
                  {access.active?.scope === "employer_need_practice"
                    ? "практику компании"
                    : "попытку"}
                  .{" "}
                  <Link
                    className="link-action"
                    href={`/assessment/${access.active?.id}`}
                  >
                    Продолжить текущую попытку
                  </Link>
                </Notice>
              ) : !access.allowed && access.policy ? (
                <Notice tone="amber">
                  Новая попытка пока недоступна.{" "}
                  {access.policy.next_allowed_at
                    ? `Доступна ${new Date(access.policy.next_allowed_at).toLocaleString("ru-RU")}.`
                    : "Сервер уточнит дату доступности."}{" "}
                  Ранее подтверждённая категория сохраняется.
                </Notice>
              ) : access.resumeId ? (
                <Notice>
                  Незавершённая попытка сохранена. Продолжение не сбрасывает
                  серверный таймер.
                </Notice>
              ) : null}
              <Button
                variant="ghost"
                onClick={() => void availability.reload()}
              >
                Обновить доступность
              </Button>
              {error !== undefined && <ErrorBox error={error} />}
              <div className="row top-gap v-form-actions">
                <Button variant="secondary" onClick={() => setStep(1)}>
                  Изменить маршрут
                </Button>
                <Button
                  busy={busy}
                  disabled={
                    !access.allowed ||
                    availability.loading ||
                    availability.error !== undefined
                  }
                  onClick={() =>
                    access.resumeId
                      ? router.push(`/assessment/${access.resumeId}`)
                      : void start()
                  }
                >
                  {access.resumeId ? "Продолжить экзамен" : "Начать экзамен"}{" "}
                  <ArrowRight size={16} />
                </Button>
              </div>
            </div>
          )}
        </div>
        <aside className="linear-column v-inspector">
          <div className="panel">
            <div className="panel-header">
              <h2>Что будет проверено</h2>
              <ClipboardIcon />
            </div>
            {(selected?.competencies || []).map((c: unknown, i: number) => (
              <div
                className="linear-record-row v-record v-record-competency"
                key={i}
              >
                <div className="v-record-content">
                  <strong>
                    {competencyLabel(
                      typeof c === "string"
                        ? c
                        : (c as Dict).label || String((c as Dict).id),
                    )}
                  </strong>
                </div>
                <ShieldCheck size={18} className="muted v-record-icon" />
              </div>
            ))}
            {!selected?.competencies?.length && (
              <p>
                Знания, практические действия, анализ и надёжность решений в
                выбранном направлении.
              </p>
            )}
          </div>
          <div className="panel">
            <h3>Если уровень не подтвердится</h3>
            <p>
              Ты получишь разбор компетенций и сможешь добровольно выбрать
              уровень ниже. Ранее подтверждённая категория сохраняется.
            </p>
            <div className="safe-data-note">
              <LockKeyhole size={14} />
              Результаты попыток видны тебе; компании видят допустимые
              подтверждения паспорта.
            </div>
          </div>
          <Notice tone="amber">
            Исполнение произвольного кода доступно только с подключённым
            изолированным runner. Сейчас{" "}
            {catalog.data?.judge_available
              ? "runner подключён"
              : "используются безопасные задачи с данными и структурированными ответами"}
            .
          </Notice>
        </aside>
      </div>
    </>
  );
}
function ClipboardIcon() {
  return <FileText size={17} className="muted" />;
}
export function HistoryPage(ctx: WorkspaceContext) {
  const [attemptPage, setAttemptPage] = useState(1);
  const [surveyPage, setSurveyPage] = useState(1);
  const pageSize = 30;
  const { data, error, loading, reload } = useResource<Dict>(
    `/candidate/history?page=${attemptPage}&page_size=${pageSize}`,
  );
  const survey = useResource<Dict>(
    `/candidate/survey-history?page=${surveyPage}&page_size=${pageSize}`,
  );
  const [tab, setTab] = useState("attempts");
  const list = items(data);
  const attemptLoading =
    loading || (typeof data?.page === "number" && data.page !== attemptPage);
  const surveyLoading =
    survey.loading ||
    (typeof survey.data?.page === "number" && survey.data.page !== surveyPage);
  return (
    <>
      <PageTitle
        title="История результатов"
        description="Каждая попытка сохраняет свой маршрут, условия и версию проверки."
        action={
          <Link href="/workspace/assessment" className="button primary">
            Новый экзамен <ArrowRight size={15} />
          </Link>
        }
      />
      <div
        className="linear-pill-tabs v-view-tabs"
        role="group"
        aria-label="Раздел истории"
      >
        <button
          className={tab === "attempts" ? "active" : ""}
          aria-pressed={tab === "attempts"}
          onClick={() => setTab("attempts")}
        >
          Попытки проверки
        </button>
        <button
          className={tab === "surveys" ? "active" : ""}
          aria-pressed={tab === "surveys"}
          onClick={() => setTab("surveys")}
        >
          Опросы и маршруты
        </button>
      </div>
      {tab === "surveys" ? (
        <div className="linear-record-list v-record-list">
          {surveyLoading ? (
            <Loading label="Загружаем сохранённые маршруты" />
          ) : survey.error !== undefined ? (
            <ErrorBox error={survey.error} retry={() => void survey.reload()} />
          ) : items(survey.data).length ? (
            items(survey.data).map((s) => (
              <div
                className="linear-record-row v-record v-record-survey"
                key={s.id}
              >
                <div className="v-record-content">
                  <h3>
                    {date(s.created_at)} ·{" "}
                    {s.answers
                      ? specName(s.answers.specialization)
                      : "Архивный опрос"}
                  </h3>
                  {s.snapshot_available && s.answers ? (
                    <>
                      <p>
                        Предполагаемый уровень: {gradeName(s.answers.grade)} ·{" "}
                        {formats.find(
                          ([v]) => v === s.answers.work_format,
                        )?.[1] || s.answers.work_format}
                      </p>
                      <p>
                        Контекст:{" "}
                        {(
                          {
                            product: "Продуктовая разработка",
                            fintech: "Финтех",
                            ecommerce: "Электронная коммерция",
                            enterprise: "Корпоративные системы",
                            public: "Государственные сервисы",
                            any: "Любой контекст",
                          } as Record<string, string>
                        )[s.answers.industry] || s.answers.industry}
                      </p>
                      <div className="tags">
                        {(s.answers.stack || []).map((skill: string) => (
                          <Tag key={skill}>{skill}</Tag>
                        ))}
                      </div>
                    </>
                  ) : (
                    <p>
                      В старой записи не сохранён снимок ответов. Текущий
                      профиль не подставляется вместо него.
                    </p>
                  )}
                  <small className="muted v-record-meta">
                    Справочник: {s.taxonomy_version || "Версия не сохранена"}.
                    Опрос сам по себе не подтверждает грейд.
                  </small>
                </div>
              </div>
            ))
          ) : (
            <Empty
              title={
                survey.data?.total > 0
                  ? "На этой странице нет опросов"
                  : "Опросов пока нет"
              }
              text={
                survey.data?.total > 0
                  ? "Вернись на предыдущую страницу, чтобы открыть сохранённые маршруты."
                  : "После сохранения маршрута здесь останутся ответы и версия справочника."
              }
            />
          )}
          {!surveyLoading && survey.error === undefined && (
            <HistoryPagination
              label="Страницы опросов"
              data={survey.data}
              page={surveyPage}
              pageSize={pageSize}
              onPage={setSurveyPage}
            />
          )}
        </div>
      ) : (
        <div className="linear-section">
          {attemptLoading ? (
            <Loading label="Загружаем попытки" />
          ) : error !== undefined ? (
            <ErrorBox error={error} retry={() => void reload()} />
          ) : list.length ? (
            <div
              className="v-table-scroll"
              style={{ overflowX: "auto" }}
              role="region"
              aria-label="История попыток"
              tabIndex={0}
            >
              <table className="details-table v-history-table">
                <caption className="v-table-caption">
                  Сохранённые попытки
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Маршрут</th>
                    <th scope="col">Дата</th>
                    <th scope="col">Результат</th>
                    <th scope="col">Статус</th>
                    <th scope="col">Действия</th>
                  </tr>
                </thead>
                <tbody>
                  {list.map((a) => (
                    <tr key={a.id}>
                      <td>
                        <strong>{specName(a.specialization)}</strong>
                        <br />
                        <small className="muted">{gradeName(a.grade)}</small>
                        {assessmentKind(a) !== "global_category" && (
                          <>
                            <br />
                            <small className="muted">
                              {assessmentKind(a) === "need_practice"
                                ? "Практика компании · категория не меняется"
                                : "Демонстрация · категория не меняется"}
                            </small>
                          </>
                        )}
                      </td>
                      <td>{date(a.started_at || a.created_at)}</td>
                      <td>
                        {a.result?.score ?? a.score ?? "—"}
                        {a.result?.score !== undefined ? " / 100" : ""}
                      </td>
                      <td>
                        <Badge
                          tone={
                            a.result?.passed || a.passed
                              ? "green"
                              : ["active", "in_progress"].includes(a.status)
                                ? "purple"
                                : "neutral"
                          }
                        >
                          {assessmentStatus(a)}
                        </Badge>
                      </td>
                      <td>
                        <Link
                          className="link-action"
                          href={`/assessment/${a.id}`}
                        >
                          {["active", "in_progress"].includes(a.status)
                            ? "Продолжить"
                            : "Подробнее"}
                          <ArrowRight size={13} />
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty
              title={
                data?.total > 0
                  ? "На этой странице нет попыток"
                  : "Начнём твою историю"
              }
              text={
                data?.total > 0
                  ? "Вернись на предыдущую страницу, чтобы открыть сохранённые результаты."
                  : "После первого экзамена здесь появится результат и разбор компетенций."
              }
              icon="check"
              action={
                <Link className="button primary" href="/workspace/assessment">
                  Выбрать маршрут
                </Link>
              }
            />
          )}
          {!attemptLoading && error === undefined && (
            <HistoryPagination
              label="Страницы попыток"
              data={data}
              page={attemptPage}
              pageSize={pageSize}
              onPage={setAttemptPage}
            />
          )}
        </div>
      )}
    </>
  );
}

function HistoryPagination({
  label,
  data,
  page,
  pageSize,
  onPage,
}: {
  label: string;
  data: Dict | null;
  page: number;
  pageSize: number;
  onPage: (page: number) => void;
}) {
  const total = data?.total ?? items(data).length;
  const count = items(data).length;
  const from = count ? (page - 1) * pageSize + 1 : 0;
  const to = count ? from + count - 1 : 0;
  return (
    <nav className="row between top-gap v-pagination" aria-label={label}>
      <small className="muted" role="status">
        Показано {from}–{to} из {total}
      </small>
      <div className="inline v-form-actions">
        <Button
          variant="secondary"
          disabled={page <= 1}
          onClick={() => onPage(page - 1)}
        >
          Предыдущая
        </Button>
        <Button
          variant="secondary"
          disabled={page * pageSize >= total}
          onClick={() => onPage(page + 1)}
        >
          Следующая
        </Button>
      </div>
    </nav>
  );
}

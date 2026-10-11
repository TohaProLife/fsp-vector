"use client";
import { useState, useEffect, useRef } from "react";
import {
  Send,
  Check,
  Plus,
  ArrowRight,
  Building2,
  Clock,
  ShieldCheck,
  LockKeyhole,
  MessageSquare,
  BriefcaseBusiness,
  FlaskConical,
  Search,
  ChevronRight,
  ExternalLink,
  Circle,
  CheckCircle2,
  RefreshCw,
} from "lucide-react";
import {
  api,
  post,
  patch,
  Dict,
  Need,
  items,
  money,
  date,
  statusName,
  specName,
  gradeName,
  specLabels,
  safeURL,
} from "@/lib/api";
import { useResource, useDomainRefresh } from "@/lib/hooks";
import {
  PageTitle,
  Button,
  Field,
  Loading,
  ErrorBox,
  Modal,
  Badge,
  Notice,
  Empty,
  Tag,
  Avatar,
} from "@/components/ui";
import type { WorkspaceContext } from "@/components/workspace";
import { CodePractice } from "./code-practice";
import { NeedPracticeStart } from "./need-practice";
import { weeklyState } from "@/lib/assessment-scope";
const specs = Object.entries(specLabels).filter(
  ([id]) => id !== "data_analytics",
);
export function OfferForm({
  candidate,
  need,
  onClose,
  onSaved,
}: {
  candidate: Dict;
  need?: Need;
  onClose: () => void;
  onSaved: () => void;
}) {
  const company = useResource<Dict>("/employer/company");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const submit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setBusy(true);
    setError(undefined);
    const f = new FormData(e.currentTarget);
    const from = Number(f.get("salary_from")),
      to = Number(f.get("salary_to"));
    if (from > to) {
      setError(new Error("Зарплата «до» должна быть не меньше зарплаты «от»."));
      setBusy(false);
      return;
    }
    try {
      await post("/invitations", {
        candidate_id: candidate.id,
        need_id: need?.id || null,
        title: f.get("title"),
        message: f.get("message"),
        salary_from: from,
        salary_to: to,
        work_format: f.get("work_format"),
        employment: f.get("employment"),
        contact: f.get("contact"),
      });
      onSaved();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal
      title={`Пригласить ${candidate.alias || "специалиста"}`}
      description="Персональное предложение с понятными условиями. Публиковать вакансию необязательно."
      onClose={onClose}
    >
      <form onSubmit={submit} className="form-stack">
        <div className="fsp-row">
          <Avatar name={candidate.alias} />
          <div>
            <strong>{candidate.alias}</strong>
            <small>
              {specName(candidate.specialization)} ·{" "}
              {gradeName(candidate.confirmed_grade || candidate.grade)}
            </small>
          </div>
          <Badge
            tone={
              candidate.source === "synthetic_fixture" ? "amber" : "neutral"
            }
          >
            <ShieldCheck size={11} />
            {candidate.source === "synthetic_fixture"
              ? "Демоданные"
              : "Категория в паспорте"}
          </Badge>
        </div>
        <Field label="Название предложения">
          <input
            name="title"
            defaultValue={need?.title || "Приглашение в нашу команду"}
            required
            maxLength={180}
          />
        </Field>
        <Field label="Почему приглашаете и что предстоит делать">
          <textarea
            name="message"
            required
            maxLength={6000}
            defaultValue={
              need
                ? `Предлагаем обсудить работу в команде ${need.team || company.data?.name || "продукта"}. ${need.description || ""}`
                : ""
            }
            placeholder="Расскажите о задачах, команде и следующем этапе знакомства."
          />
        </Field>
        <div className="form-grid">
          <Field label="Зарплата от, ₽ в месяц">
            <input
              type="number"
              name="salary_from"
              required
              min={1}
              max={10000000}
              defaultValue={need?.salary_from || 180000}
            />
          </Field>
          <Field label="Зарплата до, ₽ в месяц">
            <input
              type="number"
              name="salary_to"
              required
              min={1}
              max={10000000}
              defaultValue={need?.salary_to || 240000}
            />
          </Field>
          <Field label="Формат">
            <select
              name="work_format"
              defaultValue={need?.work_format || "remote"}
            >
              <option value="remote">Удалённо</option>
              <option value="hybrid">Гибрид</option>
              <option value="office">Офис</option>
            </select>
          </Field>
          <Field label="Занятость">
            <select
              name="employment"
              defaultValue={need?.employment || "full_time"}
            >
              <option value="full_time">Полная</option>
              <option value="part_time">Частичная</option>
              <option value="project">Проектная</option>
            </select>
          </Field>
        </div>
        <Field label="Контакт компании">
          <input
            name="contact"
            required
            defaultValue={company.data?.contact || ""}
            placeholder="Email или Telegram рекрутера"
          />
        </Field>
        <Notice>
          Кандидат увидит компанию, зарплату и условия до принятия. Его контакты
          откроются только вашей компании после явного согласия.
        </Notice>
        {error !== undefined && <ErrorBox error={error} />}
        <Button type="submit" busy={busy}>
          <Send size={15} /> Отправить приглашение
        </Button>
      </form>
    </Modal>
  );
}
export function Invitations(ctx: WorkspaceContext) {
  const { data, error, loading, reload } = useResource<Dict>("/invitations");
  const [tab, setTab] = useState("all");
  const [detail, setDetail] = useState<Dict | null>(null);
  const [detailError, setDetailError] = useState<unknown>();
  const detailGeneration = useRef(0);
  useEffect(
    () => () => {
      detailGeneration.current++;
    },
    [],
  );
  const employer = ctx.me.role === "employer";
  const list = items(data);
  const visible = list.filter(
    (i) =>
      tab === "all" ||
      (tab === "active"
        ? ["sent", "viewed", "pending"].includes(i.status)
        : i.status === tab),
  );
  const open = async (i: Dict) => {
    const request = ++detailGeneration.current;
    setDetail({ ...i, _loading: true });
    setDetailError(undefined);
    try {
      const response = await api(`/invitations/${i.id}`);
      if (request !== detailGeneration.current) return;
      setDetail(response);
      void reload();
    } catch (e) {
      if (request !== detailGeneration.current) return;
      setDetailError(e);
      setDetail((current) =>
        current?.id === i.id ? { ...current, _loading: false } : current,
      );
    }
  };
  const syncInvitations = async () => {
    void reload();
    if (!detail) return;
    const request = ++detailGeneration.current;
    try {
      const response = await api(`/invitations/${detail.id}`);
      if (request === detailGeneration.current) {
        setDetail(response);
        setDetailError(undefined);
      }
    } catch (e) {
      if (request === detailGeneration.current) setDetailError(e);
    }
  };
  useDomainRefresh(() => void syncInvitations());
  const invitationColumns = [
    {
      key: "active",
      label: "Ожидают ответа",
      values: ["sent", "viewed", "pending"],
    },
    { key: "accepted", label: "Приняты", values: ["accepted"] },
    {
      key: "closed",
      label: "Закрыты",
      values: ["declined", "withdrawn", "expired"],
    },
  ].map((column) => ({
    ...column,
    invitations: visible.filter((invitation) =>
      column.key === "closed"
        ? !["sent", "viewed", "pending", "accepted"].includes(invitation.status)
        : column.values.includes(invitation.status),
    ),
  }));
  const invitationRecord = (i: Dict) => (
    <article
      key={i.id}
      className={
        employer
          ? "linear-record v-invitation-card"
          : "linear-record-row v-opportunity-card v-invitation-card"
      }
    >
      <div className="linear-record-content">
        <div className="row between">
          <small className="muted">{date(i.created_at)}</small>
          <Badge tone={i.status === "accepted" ? "green" : "neutral"}>
            {statusName(i.status)}
            {i.viewed_at && i.status === "pending" ? " · Просмотрено" : ""}
          </Badge>
        </div>
        <h3>
          <button className="link-action" onClick={() => void open(i)}>
            {i.title || "Предложение команды"}
          </button>
        </h3>
        <p>
          {employer
            ? i.candidate?.alias || i.candidate_alias || "Специалист"
            : i.company?.name ||
              i.company_snapshot?.name ||
              i.company_name ||
              "Команда"}
        </p>
        <p className="v-opportunity-meta">
          <span>
            {money(i.salary_from)} — {money(i.salary_to)} ₽
          </span>
          <span>
            {i.work_format === "remote"
              ? "Удалённо"
              : i.work_format === "hybrid"
                ? "Гибрид"
                : "Офис"}
          </span>
        </p>
        <p className="safe-data-note">
          <LockKeyhole size={12} />
          {i.contacts_open
            ? "Контакты доступны компании"
            : i.status === "accepted"
              ? "Доступ отозван"
              : "Контакты закрыты"}
        </p>
      </div>
      <div className="linear-record-actions v-opportunity-footer">
        <Button variant="ghost" onClick={() => void open(i)}>
          Открыть <ChevronRight size={15} />
        </Button>
      </div>
    </article>
  );
  return (
    <>
      <PageTitle
        eyebrow={
          employer
            ? "Диалог с подходящими людьми"
            : "Команды выбирают твои навыки"
        }
        title={employer ? "Приглашения" : "Предложения команд"}
        description={
          employer
            ? "Отслеживайте ответы и обсуждайте условия в одном месте."
            : "Сначала условия, затем твой выбор. Контакты откроются только после принятия."
        }
        action={
          <Button
            variant="secondary"
            busy={loading}
            onClick={() => void syncInvitations()}
          >
            <RefreshCw size={14} /> Обновить
          </Button>
        }
      />
      <div className="section-tabs linear-pill-tabs">
        {[
          ["all", "Все"],
          ["active", "Ожидают ответа"],
          ["accepted", "Приняты"],
          ["declined", "Отклонены"],
        ].map(([v, l]) => (
          <button
            key={v}
            className={tab === v ? "active" : ""}
            onClick={() => setTab(v)}
            aria-pressed={tab === v}
          >
            {l}
            {v === "all" ? ` · ${list.length}` : ""}
          </button>
        ))}
      </div>
      {loading ? (
        <Loading />
      ) : error !== undefined ? (
        <ErrorBox error={error} retry={() => void reload()} />
      ) : visible.length ? (
        employer ? (
          <div className="linear-detail-layout">
            <div className="linear-detail-main">
              <div className="linear-board v-pipeline">
                {invitationColumns.map((column) => (
                  <section
                    className="linear-column"
                    key={column.key}
                    aria-label={column.label}
                  >
                    <div className="linear-column-header">
                      {column.key === "accepted" ? (
                        <CheckCircle2 size={15} />
                      ) : (
                        <Circle size={15} />
                      )}
                      <h2>{column.label}</h2>
                      <span>{column.invitations.length}</span>
                    </div>
                    {column.invitations.map(invitationRecord)}
                    {!column.invitations.length && (
                      <p className="muted">Приглашений пока нет</p>
                    )}
                  </section>
                ))}
              </div>
            </div>
            <aside className="linear-properties">
              <h2>Свойства воронки</h2>
              <div className="list-row">
                <span>Приглашений</span>
                <strong>{list.length}</strong>
              </div>
              <div className="list-row">
                <span>Показано</span>
                <strong>{visible.length}</strong>
              </div>
              <Notice>
                Доступ к контактам определяется согласием кандидата. Принятое
                приглашение не заменяет проверку текущего доступа.
              </Notice>
              <a className="link-action" href="/workspace/talent">
                Найти специалиста <ArrowRight size={14} />
              </a>
            </aside>
          </div>
        ) : (
          <div className="linear-record-list v-opportunity-list">
            {visible.map(invitationRecord)}
          </div>
        )
      ) : (
        <div className="panel">
          <Empty
            title={
              tab === "all"
                ? employer
                  ? "Первое приглашение впереди"
                  : "Новые возможности появятся здесь"
                : "В этом статусе пока пусто"
            }
            text={
              employer
                ? "Найдите специалиста в банке или подборке, откройте профиль и отправьте персональное предложение."
                : "Проверь публикацию профиля и подтверждённую категорию. Команды смогут находить твои компетенции."
            }
            icon="spark"
          />
        </div>
      )}
      {detail && (
        <InvitationDetail
          invitation={detail}
          employer={employer}
          error={detailError}
          onClose={() => {
            detailGeneration.current++;
            setDetail(null);
            setDetailError(undefined);
          }}
          onRetry={() => void open(detail)}
          onUpdated={async (message) => {
            const request = ++detailGeneration.current;
            ctx.notify(message);
            await reload();
            try {
              const response = await api(`/invitations/${detail.id}`);
              if (request === detailGeneration.current) setDetail(response);
            } catch (e) {
              if (request === detailGeneration.current) setDetailError(e);
            }
          }}
        />
      )}
    </>
  );
}
function InvitationDetail({
  invitation: i,
  employer,
  error,
  onClose,
  onRetry,
  onUpdated,
}: {
  invitation: Dict;
  employer: boolean;
  error: unknown;
  onClose: () => void;
  onRetry: () => void;
  onUpdated: (message: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<unknown>();
  const [accepting, setAccepting] = useState(false);
  const [closing, setClosing] = useState<"decline" | "withdraw" | null>(null);
  const [text, setText] = useState("");
  const [safety, setSafety] = useState<"report" | "block" | null>(null);
  const [reportText, setReportText] = useState("");
  const active = ["sent", "viewed", "pending"].includes(i.status);
  const company = i.company || i.company_snapshot || {};
  const mutate = async (action: string) => {
    setBusy(true);
    setActionError(undefined);
    try {
      await post(`/invitations/${i.id}/${action}`);
      setAccepting(false);
      onUpdated(
        action === "accept"
          ? "Предложение принято. Доступ компании открыт."
          : action === "decline"
            ? "Предложение отклонено"
            : "Приглашение отозвано",
      );
    } catch (e) {
      setActionError(e);
    } finally {
      setBusy(false);
    }
  };
  const message = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setActionError(undefined);
    try {
      await post(`/invitations/${i.id}/messages`, { text });
      setText("");
      onUpdated("Сообщение отправлено");
    } catch (e) {
      setActionError(e);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal
      wide
      title={i.title || "Предложение команды"}
      description={`${company.name || i.company_name || "Компания"} · ${statusName(i.status)}`}
      onClose={onClose}
    >
      {error !== undefined ? (
        <ErrorBox error={error} retry={onRetry} />
      ) : i._loading ? (
        <Loading />
      ) : (
        <div className="linear-detail-layout v-conversation-layout">
          <div className="linear-detail-main">
            <div className="salary">
              {money(i.salary_from)} — {money(i.salary_to)} ₽ / месяц
            </div>
            <div className="invitation-detail-grid">
              <div>
                <small>Формат работы</small>
                <strong>
                  {i.work_format === "remote"
                    ? "Удалённо"
                    : i.work_format === "hybrid"
                      ? "Гибрид"
                      : "В офисе"}
                </strong>
              </div>
              <div>
                <small>Занятость</small>
                <strong>
                  {i.employment === "full_time"
                    ? "Полная"
                    : i.employment === "part_time"
                      ? "Частичная"
                      : "Проектная"}
                </strong>
              </div>
              <div>
                <small>Контакт компании</small>
                <strong>{i.contact || company.contact || "—"}</strong>
              </div>
              <div>
                <small>Отправлено</small>
                <strong>{date(i.created_at)}</strong>
              </div>
              {i.viewed_at && (
                <div>
                  <small>Просмотрено кандидатом</small>
                  <strong>{date(i.viewed_at)}</strong>
                </div>
              )}
            </div>
            <h3>О предложении</h3>
            <p style={{ whiteSpace: "pre-wrap" }}>{i.message}</p>
            <h3 className="top-gap">О компании</h3>
            <p>
              {company.description ||
                i.company_description ||
                "Описание компании"}
            </p>
            {safeURL(company.website) && (
              <a
                className="link-action"
                href={safeURL(company.website)}
                target="_blank"
                rel="noreferrer"
              >
                Сайт компании <ExternalLink size={13} />
              </a>
            )}
            {i.reasons?.length > 0 && (
              <div className="passport-story">
                <h3>Основания совпадения</h3>
                <ul className="feedback-list">
                  {i.reasons.map((r: string, n: number) => (
                    <li key={n}>{r}</li>
                  ))}
                </ul>
              </div>
            )}
            {employer && i.candidate?.contacts && (
              <div className="top-gap">
                <Notice tone="green">
                  Доступ к контактам открыт вашей компании.
                </Notice>
                <div className="passport-story">
                  {Object.entries(i.candidate.contacts)
                    .filter(([, v]) => v)
                    .map(([k, v]) => (
                      <p key={k}>
                        {k}: {String(v)}
                      </p>
                    ))}
                </div>
              </div>
            )}
            {employer && !i.candidate?.contacts && (
              <Notice>
                Контакты сейчас закрыты для вашей компании. Доступ определяется
                действующим согласием кандидата, а не статусом приглашения.
              </Notice>
            )}
            {employer && i.content_redacted && (
              <Notice tone="amber">
                {i.privacy_reason === "company_blocked"
                  ? "Кандидат заблокировал вашу компанию. Его личные сообщения закрыты; история и ваши условия сохранены."
                  : "Кандидат отозвал согласие на обработку. Его личные сообщения закрыты; история и ваши условия сохранены."}
              </Notice>
            )}
            {!employer && i.status === "accepted" && (
              <Notice tone="green">
                Ты принял предложение. Управлять доступом компании можно в
                разделе «Приватность».
              </Notice>
            )}
            {!employer &&
              (active || i.status === "accepted") &&
              (i.need_id || i.vacancy_id || i.need_snapshot) && (
                <div className="top-gap">
                  <NeedPracticeStart invitationId={i.id} />
                </div>
              )}
            {active && (
              <div className="top-gap">
                {employer ? (
                  <Button
                    variant="secondary"
                    busy={busy}
                    onClick={() => setClosing("withdraw")}
                  >
                    Отозвать приглашение
                  </Button>
                ) : accepting ? (
                  <div className="form-stack">
                    <Notice>
                      Принятие открывает твоё имя и контакты только этой
                      компании. Позже доступ можно отозвать в настройках
                      приватности.
                    </Notice>
                    <div className="row">
                      <Button busy={busy} onClick={() => void mutate("accept")}>
                        <Check size={15} /> Принять и открыть контакт
                      </Button>
                      <Button
                        variant="ghost"
                        onClick={() => setAccepting(false)}
                      >
                        Отмена
                      </Button>
                    </div>
                  </div>
                ) : (
                  <div className="row">
                    <Button onClick={() => setAccepting(true)}>
                      <Check size={15} /> Принять предложение
                    </Button>
                    <Button
                      variant="secondary"
                      busy={busy}
                      onClick={() => setClosing("decline")}
                    >
                      Отклонить
                    </Button>
                  </div>
                )}
              </div>
            )}
            {closing && (
              <div className="passport-story">
                <h3>
                  {closing === "withdraw"
                    ? "Отозвать это приглашение?"
                    : "Отклонить это предложение?"}
                </h3>
                <p>
                  {closing === "withdraw"
                    ? "Кандидат увидит, что предложение закрыто."
                    : "Компания увидит отказ. Контакты останутся закрыты."}
                </p>
                <div className="row top-gap">
                  <Button variant="secondary" onClick={() => setClosing(null)}>
                    Отмена
                  </Button>
                  <Button
                    variant="danger"
                    busy={busy}
                    onClick={() => {
                      void mutate(closing);
                      setClosing(null);
                    }}
                  >
                    {closing === "withdraw"
                      ? "Подтвердить отзыв"
                      : "Подтвердить отказ"}
                  </Button>
                </div>
              </div>
            )}
            {actionError !== undefined && (
              <div className="top-gap">
                <ErrorBox error={actionError} />
              </div>
            )}
          </div>
          <div className="linear-properties v-conversation">
            <h3>
              <MessageSquare
                size={16}
                style={{ verticalAlign: "middle", marginRight: 7 }}
              />
              Обсудить предложение
            </h3>
            <Notice>
              Сообщение не означает принятие. Обсудите вопросы до открытия
              контактов.
            </Notice>
            <div
              className="chat-messages"
              role="log"
              aria-label="Переписка о предложении"
              aria-live="polite"
            >
              {(i.messages || []).length ? (
                (i.messages || []).map((m: Dict) => (
                  <div
                    key={m.id}
                    className={`chat-message ${m.author_role === (employer ? "employer" : "candidate") ? "is-own" : ""}`}
                  >
                    <strong>
                      {m.sender_name ||
                        m.author_name ||
                        (m.author_role === "employer"
                          ? "Команда"
                          : "Специалист") ||
                        "Участник"}
                    </strong>
                    <p>
                      {m.content_redacted
                        ? "Содержание закрыто по настройкам приватности кандидата."
                        : m.text}
                    </p>
                    <small>{date(m.created_at)}</small>
                  </div>
                ))
              ) : (
                <p className="muted no-margin">
                  Диалог ещё не начат. Можно спросить о команде, задачах и
                  этапах отбора.
                </p>
              )}
            </div>
            <form onSubmit={message} className="form-stack">
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Что хочешь уточнить?"
                required
                maxLength={3000}
                aria-label="Сообщение о приглашении"
              />
              <Button
                type="submit"
                variant="secondary"
                busy={busy}
                disabled={!text.trim()}
              >
                <Send size={14} /> Отправить сообщение
              </Button>
            </form>
            <p className="safe-data-note">
              <LockKeyhole size={13} />
              Диалог доступен только участникам этого приглашения.
            </p>
            {!employer && (
              <div className="top-gap">
                <div className="inline">
                  <Button
                    variant="ghost"
                    onClick={() =>
                      setSafety(safety === "report" ? null : "report")
                    }
                  >
                    Пожаловаться
                  </Button>
                  <Button
                    variant="ghost"
                    onClick={() =>
                      setSafety(safety === "block" ? null : "block")
                    }
                  >
                    Заблокировать компанию
                  </Button>
                </div>
                {safety && (
                  <form
                    className="form-stack top-gap"
                    onSubmit={async (e) => {
                      e.preventDefault();
                      setBusy(true);
                      setActionError(undefined);
                      try {
                        if (safety === "report") {
                          await post(`/invitations/${i.id}/report`, {
                            text: reportText,
                          });
                          onUpdated("Жалоба сохранена для проверки");
                        } else {
                          await post(
                            `/candidate/companies/${i.company_id}/block`,
                          );
                          onUpdated(
                            "Компания заблокирована. Доступ к контактам закрыт.",
                          );
                        }
                        setSafety(null);
                        setReportText("");
                      } catch (err) {
                        setActionError(err);
                      } finally {
                        setBusy(false);
                      }
                    }}
                  >
                    {safety === "report" ? (
                      <Field label="Что не так с предложением?">
                        <textarea
                          required
                          minLength={3}
                          maxLength={3000}
                          value={reportText}
                          onChange={(e) => setReportText(e.target.value)}
                          placeholder="Опиши проблему для оператора"
                        />
                      </Field>
                    ) : (
                      <Notice tone="amber">
                        Компания не сможет присылать новые предложения. Активные
                        приглашения закроются, доступ к контактам будет отозван.
                        Разблокировать её можно в разделе «Приватность».
                      </Notice>
                    )}
                    <Button variant="danger" type="submit" busy={busy}>
                      {safety === "report"
                        ? "Отправить жалобу"
                        : "Заблокировать и закрыть доступ"}
                    </Button>
                  </form>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </Modal>
  );
}
export function Jobs(ctx: WorkspaceContext) {
  const employer = ctx.me.role === "employer";
  const vacancies = useResource<Dict>("/vacancies");
  const applications = useResource<Dict>("/applications");
  const [tab, setTab] = useState("vacancies");
  const [editing, setEditing] = useState<Dict | null>(null);
  const [apply, setApply] = useState<Dict | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [search, setSearch] = useState("");
  const [selectedApplication, setSelectedApplication] = useState<string | null>(
    null,
  );
  const [updatingApplication, setUpdatingApplication] = useState<string | null>(
    null,
  );
  const list = items(vacancies.data).filter(
    (v) =>
      !search ||
      `${v.title} ${v.description} ${v.company?.name || ""}`
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  const appList = items(applications.data);
  const applicationStatuses = [
    "new",
    "review",
    "interview",
    "offer",
    "accepted",
    "rejected",
  ];
  const applicationColumns = [
    ...applicationStatuses,
    ...new Set(
      appList
        .map((application) => application.status)
        .filter((status) => !applicationStatuses.includes(status)),
    ),
  ];
  const inspectedApplication =
    appList.find((application) => application.id === selectedApplication) ||
    appList[0];
  const updateApplication = async (application: Dict, status: string) => {
    setUpdatingApplication(application.id);
    setError(undefined);
    try {
      await patch(`/applications/${application.id}`, { status });
      await applications.reload();
      ctx.notify("Статус отклика обновлён");
    } catch (err) {
      setError(err);
    } finally {
      setUpdatingApplication(null);
    }
  };
  const syncJobs = () => {
    void vacancies.reload();
    void applications.reload();
  };
  useDomainRefresh(syncJobs);
  return (
    <>
      <PageTitle
        eyebrow={
          employer ? "Ещё один путь к команде" : "Когда хочется выбрать самому"
        }
        title={employer ? "Вакансии и отклики" : "Вакансии"}
        description={
          employer
            ? "Публикуйте роли с зарплатой и отслеживайте ответы специалистов."
            : "Персональные предложения и самостоятельные отклики дополняют друг друга."
        }
        action={
          <div className="row">
            <Button
              variant="secondary"
              busy={vacancies.loading || applications.loading}
              onClick={syncJobs}
            >
              <RefreshCw size={14} /> Обновить
            </Button>
            {employer && (
              <Button onClick={() => setEditing({})}>
                <Plus size={15} /> Новая вакансия
              </Button>
            )}
          </div>
        }
      />
      <div className="section-tabs linear-pill-tabs">
        <button
          className={tab === "vacancies" ? "active" : ""}
          onClick={() => setTab("vacancies")}
          aria-pressed={tab === "vacancies"}
        >
          {employer ? "Вакансии команды" : "Все вакансии"}
        </button>
        <button
          className={tab === "applications" ? "active" : ""}
          onClick={() => setTab("applications")}
          aria-pressed={tab === "applications"}
        >
          {employer ? "Отклики специалистов" : "Мои отклики"} · {appList.length}
        </button>
      </div>
      {tab === "vacancies" ? (
        <>
          <div className="filters linear-list-toolbar v-job-filters">
            <div className="search-input">
              <Search />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Роль, технология, команда"
                aria-label="Поиск вакансий"
              />
            </div>
            {!vacancies.loading && vacancies.error === undefined && (
              <small className="muted">
                {list.length} из {items(vacancies.data).length} вакансий
              </small>
            )}
            {search && (
              <Button variant="ghost" onClick={() => setSearch("")}>
                Сбросить поиск
              </Button>
            )}
          </div>
          {vacancies.loading ? (
            <Loading />
          ) : vacancies.error !== undefined ? (
            <ErrorBox
              error={vacancies.error}
              retry={() => void vacancies.reload()}
            />
          ) : list.length ? (
            <div className="linear-record-list v-opportunity-list">
              {[true, false].map((published) => {
                const group = list.filter(
                  (vacancy) => Boolean(vacancy.published) === published,
                );
                if (!group.length) return null;
                return (
                  <section className="linear-section" key={String(published)}>
                    <div className="linear-group-heading">
                      <BriefcaseBusiness size={15} />
                      <h2>{published ? "Опубликованные" : "Черновики"}</h2>
                      <span>{group.length}</span>
                    </div>
                    {group.map((v) => (
                      <article
                        className="linear-record-row v-opportunity-card v-job-card"
                        key={v.id}
                      >
                        <div className="linear-record-content v-opportunity-body">
                          <div className="v-job-company">
                            <span className="company-symbol" aria-hidden="true">
                              {String(
                                v.company?.name || v.company_name || "Команда",
                              ).slice(0, 1)}
                            </span>
                            <span>
                              {v.company?.name || v.company_name || "Команда"}
                            </span>
                          </div>
                          <h3>{v.title}</h3>
                          <p className="v-opportunity-meta">
                            <span>{specName(v.specialization)}</span>
                            <span>{gradeName(v.grade)}</span>
                          </p>
                          <p className="v-opportunity-excerpt">
                            {v.description?.slice(0, 220)}
                            {v.description?.length > 220 ? "…" : ""}
                          </p>
                          <details>
                            <summary className="link-action">
                              Задачи и требования
                            </summary>
                            <p>{v.description}</p>
                            <div className="tags">
                              {(v.skills || v.required_skills || []).map(
                                (s: string) => (
                                  <Tag key={s}>{s}</Tag>
                                ),
                              )}
                            </div>
                          </details>
                        </div>
                        <div className="linear-record-meta v-opportunity-meta">
                          <span>
                            {v.work_format === "remote"
                              ? "Удалённо"
                              : v.work_format === "hybrid"
                                ? "Гибрид"
                                : "Офис"}
                          </span>
                          <strong className="v-opportunity-salary">
                            {money(v.salary_from)} — {money(v.salary_to)} ₽
                          </strong>
                        </div>
                        <div className="linear-record-actions v-opportunity-footer">
                          {employer ? (
                            <Button
                              variant="secondary"
                              onClick={() => setEditing(v)}
                            >
                              Изменить
                            </Button>
                          ) : (
                            <div className="buttons">
                              <NeedPracticeStart vacancyId={v.id} />
                              <Button onClick={() => setApply(v)}>
                                Откликнуться <ArrowRight size={15} />
                              </Button>
                            </div>
                          )}
                        </div>
                      </article>
                    ))}
                  </section>
                );
              })}
            </div>
          ) : (
            <div className="panel">
              <Empty
                title={
                  search ? "Вакансии не найдены" : "Здесь пока нет вакансий"
                }
                text={
                  search
                    ? "Попробуйте другую роль, технологию или название команды."
                    : employer
                      ? "Создайте первую роль с зарплатным диапазоном и задачами."
                      : "Попробуй позже. Персональные предложения появятся в отдельном разделе."
                }
                action={
                  search ? (
                    <Button variant="secondary" onClick={() => setSearch("")}>
                      Сбросить поиск
                    </Button>
                  ) : employer ? (
                    <Button onClick={() => setEditing({})}>
                      Создать вакансию
                    </Button>
                  ) : undefined
                }
              />
            </div>
          )}
        </>
      ) : applications.loading ? (
        <Loading />
      ) : applications.error !== undefined ? (
        <ErrorBox error={applications.error} />
      ) : appList.length ? (
        employer ? (
          <div className="linear-detail-layout">
            <div className="linear-detail-main">
              <div className="linear-board v-pipeline v-applications-pipeline">
                {applicationColumns.map((status) => {
                  const group = appList.filter(
                    (application) => application.status === status,
                  );
                  return (
                    <section
                      className="linear-column"
                      key={status}
                      aria-label={statusName(status)}
                    >
                      <div className="linear-column-header">
                        {status === "accepted" ? (
                          <CheckCircle2 size={15} />
                        ) : (
                          <Circle size={15} />
                        )}
                        <h2>{statusName(status)}</h2>
                        <span>{group.length}</span>
                      </div>
                      {group.map((a) => (
                        <article
                          className={`linear-record v-application-card ${inspectedApplication?.id === a.id ? "selected" : ""}`}
                          key={a.id}
                        >
                          <small className="muted">{date(a.created_at)}</small>
                          <h3>
                            <button
                              className="link-action"
                              onClick={() => setSelectedApplication(a.id)}
                              aria-pressed={inspectedApplication?.id === a.id}
                            >
                              {a.candidate?.alias ||
                                a.candidate_alias ||
                                "Специалист"}
                            </button>
                          </h3>
                          <p>
                            {a.vacancy?.title || a.vacancy_title || a.title}
                          </p>
                          <p className="safe-data-note">
                            <LockKeyhole size={12} />
                            {a.candidate?.contacts
                              ? "Доступ разрешён"
                              : "Контакты закрыты"}
                          </p>
                          <select
                            value={a.status}
                            disabled={updatingApplication !== null}
                            onChange={(e) =>
                              void updateApplication(a, e.target.value)
                            }
                            aria-label={`Статус отклика ${a.candidate?.alias || a.candidate_alias || "специалиста"}`}
                          >
                            {Array.from(
                              new Set([a.status, ...applicationStatuses]),
                            ).map((s) => (
                              <option key={s} value={s}>
                                {statusName(s)}
                              </option>
                            ))}
                          </select>
                        </article>
                      ))}
                      {!group.length && (
                        <p className="muted">Откликов пока нет</p>
                      )}
                    </section>
                  );
                })}
              </div>
            </div>
            <aside className="linear-properties">
              <h2>Свойства отклика</h2>
              <div className="list-row">
                <span>Специалист</span>
                <strong>
                  {inspectedApplication.candidate?.alias ||
                    inspectedApplication.candidate_alias ||
                    "Специалист"}
                </strong>
              </div>
              <div className="list-row">
                <span>Вакансия</span>
                <strong>
                  {inspectedApplication.vacancy?.title ||
                    inspectedApplication.vacancy_title ||
                    inspectedApplication.title}
                </strong>
              </div>
              <div className="list-row">
                <span>Статус</span>
                <Badge>{statusName(inspectedApplication.status)}</Badge>
              </div>
              <div className="list-row">
                <span>Получен</span>
                <span>{date(inspectedApplication.created_at)}</span>
              </div>
              {inspectedApplication.candidate?.contacts ? (
                <section className="linear-section">
                  <h3>Разрешённые контакты</h3>
                  {Object.entries(inspectedApplication.candidate.contacts)
                    .filter(([, value]) => value)
                    .map(([key, value]) => (
                      <div className="list-row" key={key}>
                        <span>{key}</span>
                        <span>{String(value)}</span>
                      </div>
                    ))}
                </section>
              ) : (
                <Notice>
                  Контакты закрыты. Текущий доступ проверяется сервером по
                  согласию кандидата.
                </Notice>
              )}
              {inspectedApplication.content_redacted && (
                <Notice tone="amber">
                  {inspectedApplication.privacy_reason === "company_blocked"
                    ? "Компания заблокирована кандидатом. Личные данные отклика закрыты."
                    : "Согласие кандидата отозвано. Личные данные отклика закрыты."}
                </Notice>
              )}
              <p className="safe-data-note">
                Перемещение по этапам сохраняется через выбор статуса в отклике.
              </p>
            </aside>
          </div>
        ) : (
          <div className="linear-record-list v-opportunity-list v-application-list">
            {appList.map((a) => (
              <article
                className="linear-record-row v-opportunity-card v-application-card"
                key={a.id}
              >
                <div className="linear-record-content v-opportunity-body">
                  <p className="v-job-company">
                    {a.vacancy?.company?.name ||
                      a.company?.name ||
                      a.company_name ||
                      "Компания"}
                  </p>
                  <h3>{a.vacancy?.title || a.vacancy_title || a.title}</h3>
                  <p className="v-opportunity-meta">
                    Отправлен {date(a.created_at)}
                  </p>
                </div>
                <div className="linear-record-meta">
                  <Badge
                    tone={
                      a.status === "accepted" || a.status === "hired"
                        ? "green"
                        : "purple"
                    }
                  >
                    {statusName(a.status)}
                  </Badge>
                </div>
              </article>
            ))}
          </div>
        )
      ) : (
        <div className="panel">
          <Empty
            title="Откликов пока нет"
            text={
              employer
                ? "Отклики специалистов появятся после публикации вакансии."
                : "Выбери подходящую вакансию и отправь отклик."
            }
          />
        </div>
      )}
      {error !== undefined && (
        <div className="top-gap">
          <ErrorBox error={error} />
        </div>
      )}
      {editing && (
        <VacancyEditor
          value={editing}
          onClose={() => setEditing(null)}
          onSaved={async () => {
            setEditing(null);
            await vacancies.reload();
            ctx.notify("Вакансия сохранена");
          }}
        />
      )}
      {apply && (
        <Modal
          title={`Отклик на «${apply.title}»`}
          description="Перед отправкой проверь, какие данные будут доступны компании."
          onClose={() => setApply(null)}
        >
          <form
            className="form-stack"
            onSubmit={async (e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              setBusy(true);
              setError(undefined);
              try {
                await post(`/vacancies/${apply.id}/apply`, {
                  message: f.get("message"),
                  consent_contacts: true,
                });
                setApply(null);
                await applications.reload();
                ctx.notify("Отклик отправлен. Доступ компании открыт.");
              } catch (err) {
                setError(err);
              } finally {
                setBusy(false);
              }
            }}
          >
            <Notice>
              Отклик открывает этой компании имя, резюме и контакты. Другие
              компании не получают доступ.
            </Notice>
            <Field label="Сопроводительное сообщение">
              <textarea
                name="message"
                maxLength={3000}
                placeholder="Почему интересна эта задача?"
              />
            </Field>
            <label className="check-label">
              <input type="checkbox" required />
              <span>
                Даю этой компании доступ к моим контактам для обсуждения
                вакансии.
              </span>
            </label>
            {error !== undefined && <ErrorBox error={error} />}
            <Button type="submit" busy={busy}>
              Отправить отклик <Send size={15} />
            </Button>
          </form>
        </Modal>
      )}
    </>
  );
}
function VacancyEditor({
  value,
  onClose,
  onSaved,
}: {
  value: Dict;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const submit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setBusy(true);
    setError(undefined);
    const f = new FormData(e.currentTarget);
    const body = {
      ...Object.fromEntries(f.entries()),
      published: f.get("published") === "true",
      salary_from: Number(f.get("salary_from")),
      salary_to: Number(f.get("salary_to")),
      skills: String(f.get("skills") || "")
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
    };
    try {
      value.id
        ? await patch(`/vacancies/${value.id}`, body)
        : await post("/vacancies", body);
      onSaved();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal
      title={value.id ? "Изменить вакансию" : "Новая вакансия"}
      description="Для публикации укажите диапазон зарплаты, компанию и задачи."
      onClose={onClose}
    >
      <form className="form-stack" onSubmit={submit}>
        <Field label="Название роли">
          <input
            name="title"
            required
            defaultValue={value.title || ""}
            placeholder="Backend-разработчик"
            maxLength={180}
          />
        </Field>
        <Field label="Задачи и условия">
          <textarea
            name="description"
            required
            defaultValue={value.description || ""}
            maxLength={6000}
          />
        </Field>
        <div className="form-grid">
          <Field label="Специализация">
            <select
              name="specialization"
              defaultValue={value.specialization || "backend"}
            >
              {specs.map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Грейд">
            <select name="grade" defaultValue={value.grade || "middle"}>
              {["intern", "junior", "middle", "senior"].map((g) => (
                <option key={g} value={g}>
                  {gradeName(g)}
                </option>
              ))}
            </select>
          </Field>
        </div>
        <Field label="Навыки, через запятую">
          <input name="skills" defaultValue={(value.skills || []).join(", ")} />
        </Field>
        <div className="form-grid">
          <Field label="Зарплата от, ₽">
            <input
              name="salary_from"
              type="number"
              min={1}
              required
              defaultValue={value.salary_from || 180000}
            />
          </Field>
          <Field label="Зарплата до, ₽">
            <input
              name="salary_to"
              type="number"
              min={1}
              required
              defaultValue={value.salary_to || 240000}
            />
          </Field>
          <Field label="Формат">
            <select
              name="work_format"
              defaultValue={value.work_format || "remote"}
            >
              <option value="remote">Удалённо</option>
              <option value="hybrid">Гибрид</option>
              <option value="office">Офис</option>
            </select>
          </Field>
          <Field label="Занятость">
            <select
              name="employment"
              defaultValue={value.employment || "full_time"}
            >
              <option value="full_time">Полная</option>
              <option value="part_time">Частичная</option>
              <option value="project">Проектная</option>
            </select>
          </Field>
          <Field label="Статус">
            <select
              name="published"
              defaultValue={String(value.published ?? true)}
            >
              <option value="false">Черновик</option>
              <option value="true">Опубликована</option>
            </select>
          </Field>
        </div>
        {error !== undefined && <ErrorBox error={error} />}
        <Button type="submit" busy={busy}>
          Сохранить вакансию <Check size={15} />
        </Button>
      </form>
    </Modal>
  );
}
export function Practice(ctx: WorkspaceContext) {
  const employer = ctx.me.role === "employer";
  const [programming, setProgramming] = useState(false);
  const { data, error, loading, reload } = useResource<Dict>("/challenges");
  const [detail, setDetail] = useState<Dict | null>(null);
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<unknown>();
  const [result, setResult] = useState<Dict | null>(null);
  const [answer, setAnswer] = useState("");
  const [reviewing, setReviewing] = useState<string | null>(null);
  const [weeklyVersion, setWeeklyVersion] = useState(0);
  const detailGeneration = useRef(0);
  useEffect(
    () => () => {
      detailGeneration.current++;
    },
    [],
  );
  const open = async (c: Dict) => {
    const request = ++detailGeneration.current;
    setDetail({ ...c, _loading: true });
    setActionError(undefined);
    setResult(null);
    setAnswer("");
    try {
      const task = await api(`/challenges/${c.id}`);
      if (request !== detailGeneration.current) return;
      setResult(
        task.last_result?.passed || task.grading !== "objective_declarative"
          ? task.last_result || null
          : null,
      );
      setDetail({
        ...task,
        item: task.public_task,
        prompt: task.public_task?.prompt || task.description,
      });
    } catch (e) {
      if (request !== detailGeneration.current) return;
      setActionError(e);
      setDetail((current) =>
        current?.id === c.id
          ? { ...current, _loading: false, _loadFailed: true }
          : current,
      );
    }
  };
  if (programming && !employer)
    return (
      <>
        <PageTitle
          eyebrow="Практика с реальными границами"
          title="Практика"
          description="Код проверяется только в изолированной среде. Глобальная категория не меняется."
        />
        <div className="section-tabs linear-pill-tabs">
          <button onClick={() => setProgramming(false)}>
            Задачи с данными
          </button>
          <button className="active" aria-pressed="true">
            Программирование
          </button>
        </div>
        <CodePractice {...ctx} />
      </>
    );
  return (
    <>
      <PageTitle
        eyebrow={
          employer
            ? "Короткая практика для знакомства"
            : "Навыки любят движение"
        }
        title={employer ? "Задачи команды" : "Практика"}
        description="Короткие задачи дают дополнительное наблюдение. Они не меняют глобальный грейд."
        action={
          employer ? (
            <Button onClick={() => setCreating(true)}>
              <Plus size={15} /> Новая задача
            </Button>
          ) : undefined
        }
      />
      {!employer && (
        <div className="section-tabs linear-pill-tabs">
          <button className="active" aria-pressed="true">
            Задачи с данными
          </button>
          <button aria-pressed="false" onClick={() => setProgramming(true)}>
            Программирование
          </button>
        </div>
      )}
      <Notice>
        Результат практики отделён от экзамена. Задача работодателя не
        становится подтверждённой глобальной категорией.
      </Notice>
      {!employer && (
        <WeeklyPractice key={weeklyVersion} onOpen={(c) => void open(c)} />
      )}
      {loading ? (
        <Loading />
      ) : error !== undefined ? (
        <div className="top-gap">
          <ErrorBox error={error} retry={() => void reload()} />
        </div>
      ) : items(data).length ? (
        <div className="linear-record-list v-opportunity-list top-gap">
          <div className="linear-group-heading">
            <FlaskConical size={15} />
            <h2>{employer ? "Задачи компании" : "Доступные задачи"}</h2>
            <span>{items(data).length}</span>
          </div>
          {items(data).map((c) => (
            <article
              key={c.id}
              className="linear-record-row v-opportunity-card v-practice-card"
            >
              <div className="linear-record-content v-opportunity-body">
                <h3>{c.title}</h3>
                <p>{c.description?.slice(0, 160) || c.prompt?.slice(0, 160)}</p>
              </div>
              <div className="linear-record-meta v-opportunity-meta">
                <div className="tags">
                  <Tag>{specName(c.specialization)}</Tag>
                  <Tag>
                    {c.public_task?.competency_label || c.skill || "Практика"}
                  </Tag>
                  <Badge>{c.duration_minutes || 10} мин</Badge>
                </div>
              </div>
              <div className="linear-record-actions v-opportunity-footer">
                <Button variant="secondary" onClick={() => void open(c)}>
                  {employer ? "Открыть задачу" : "Попробовать"}
                  <ArrowRight size={14} />
                </Button>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <div className="panel top-gap">
          <Empty
            title="Задачи скоро появятся"
            text={
              employer
                ? "Создайте короткую учебную задачу с понятным контекстом."
                : "Здесь будут небольшие задачи для поддержания навыков."
            }
            icon="spark"
          />
        </div>
      )}
      {creating && (
        <ChallengeEditor
          onClose={() => setCreating(false)}
          onSaved={async () => {
            setCreating(false);
            await reload();
            ctx.notify("Задача опубликована");
          }}
        />
      )}
      {detail && (
        <Modal
          wide
          title={detail.title || "Практическая задача"}
          description={`${specName(detail.specialization)} · ${detail.duration_minutes || 10} минут`}
          onClose={() => {
            detailGeneration.current++;
            setDetail(null);
          }}
        >
          {detail._loading ? (
            <Loading />
          ) : detail._loadFailed ? (
            <ErrorBox error={actionError} retry={() => void open(detail)} />
          ) : (
            <div className="form-stack">
              <Notice tone="amber">
                Практика не присваивает грейд.{" "}
                {detail.grading === "objective_declarative"
                  ? "Объективная проверка по версионированной задаче."
                  : "Задача компании: результат не считается независимой проверкой компетенции."}
              </Notice>
              <p className="question-prompt">
                {detail.prompt || detail.description}
              </p>
              {detail.item?.options?.length ? (
                <div role="group" aria-label="Ответ на задачу">
                  {detail.item.options.map((o: Dict) => (
                    <label
                      key={o.id}
                      className={`option ${answer === o.id ? "selected" : ""}`}
                    >
                      <input
                        type="radio"
                        name="practice"
                        value={o.id}
                        checked={answer === o.id}
                        disabled={employer || !!result}
                        onChange={() => setAnswer(o.id)}
                      />
                      {o.label}
                    </label>
                  ))}
                </div>
              ) : (
                <Field
                  label={
                    detail.item?.type === "sql" ? "SQL-запрос" : "Твой ответ"
                  }
                >
                  <textarea
                    className="code-input"
                    value={answer}
                    onChange={(e) => setAnswer(e.target.value)}
                    placeholder={
                      detail.item?.starter_code ||
                      "Формат ответа указан в условии"
                    }
                    disabled={employer || !!result}
                  />
                </Field>
              )}
              {detail.item?.public_cases && (
                <details>
                  <summary className="link-action">Данные задачи</summary>
                  <pre
                    className="code-input"
                    style={{
                      whiteSpace: "pre-wrap",
                      padding: 15,
                      minHeight: 0,
                    }}
                  >
                    {JSON.stringify(detail.item.public_cases, null, 2)}
                  </pre>
                </details>
              )}
              {actionError !== undefined && <ErrorBox error={actionError} />}{" "}
              {!employer && !result && (
                <Button
                  busy={busy}
                  disabled={!answer.trim()}
                  onClick={async () => {
                    const request = detailGeneration.current;
                    setBusy(true);
                    setActionError(undefined);
                    try {
                      const r = await post(`/challenges/${detail.id}/submit`, {
                        answer,
                      });
                      if (request !== detailGeneration.current) return;
                      setResult(r.result || r);
                      await reload();
                      setWeeklyVersion((v) => v + 1);
                      ctx.notify("Ответ сохранён");
                    } catch (e) {
                      if (request === detailGeneration.current)
                        setActionError(e);
                    } finally {
                      setBusy(false);
                    }
                  }}
                >
                  Отправить решение <ArrowRight size={15} />
                </Button>
              )}
              {employer && (
                <Button
                  variant="secondary"
                  onClick={() => setReviewing(detail.id)}
                >
                  Открыть решения специалистов <ArrowRight size={14} />
                </Button>
              )}
              {result && (
                <Notice
                  tone={
                    result.passed || result.score >= 60 ? "green" : "purple"
                  }
                >
                  <strong>
                    {result.score !== undefined && result.score !== null
                      ? `Результат: ${Math.round(result.score)} / 100`
                      : "Ответ получен"}
                  </strong>
                  <p>
                    {result.feedback ||
                      result.message ||
                      "Результат сохранён отдельно от категории."}
                  </p>
                </Notice>
              )}
            </div>
          )}
        </Modal>
      )}
      {reviewing && (
        <ChallengeReview
          challengeId={reviewing}
          onClose={() => setReviewing(null)}
          notify={ctx.notify}
        />
      )}
    </>
  );
}

function WeeklyPractice({ onOpen }: { onOpen: (challenge: Dict) => void }) {
  const { data, loading, error, reload } =
    useResource<Dict>("/challenges/weekly");
  if (loading) return <Loading label="Проверяем задание недели" />;
  if (error !== undefined)
    return (
      <div className="top-gap">
        <ErrorBox error={error} retry={() => void reload()} />
      </div>
    );
  const state = weeklyState(data || {});
  return (
    <div className="linear-section top-gap">
      <div className="panel-header">
        <h3>Задание недели · {data?.week_id}</h3>
        <Badge tone={state.completed ? "green" : "purple"}>
          {state.completed ? "Выполнено" : "Короткая практика"}
        </Badge>
      </div>
      <p>{data?.challenge?.title}</p>
      <p>
        Следующая задача: {date(data?.next_week_at)}. Результат обновляет
        отдельное наблюдение и не меняет глобальную категорию.
      </p>
      {data?.submission && (
        <p>
          Последний результат: {data.submission.result?.score ?? "—"} / 100 ·{" "}
          {date(data.submission.created_at)}
        </p>
      )}
      {state.retryBlocked && (
        <Notice tone="amber">
          Повторная попытка доступна{" "}
          {new Date(data!.retry_at).toLocaleString("ru-RU")}. Неуспешный ответ
          уже сохранён.
        </Notice>
      )}
      <div className="buttons top-gap">
        <Button
          variant="secondary"
          disabled={!data?.challenge?.id || state.retryBlocked || state.notOpen}
          onClick={() => onOpen(data!.challenge)}
        >
          {state.completed ? "Посмотреть результат" : "Открыть задание"}{" "}
          <ArrowRight size={14} />
        </Button>
        <a className="link-action" href="/workspace/privacy">
          Настроить напоминания
        </a>
      </div>
    </div>
  );
}
function ChallengeReview({
  challengeId,
  onClose,
  notify,
}: {
  challengeId: string;
  onClose: () => void;
  notify: (message: string) => void;
}) {
  const { data, error, loading, reload } = useResource<Dict>(
    `/challenges/${challengeId}/submissions`,
  );
  const [busy, setBusy] = useState(false);
  const [mutationError, setMutationError] = useState<unknown>();
  return (
    <Modal
      wide
      title="Решения специалистов"
      description="Ручная оценка компании хранится отдельно. Она не присваивает глобальный грейд и не становится независимым подтверждением."
      onClose={onClose}
    >
      {loading ? (
        <Loading />
      ) : error !== undefined ? (
        <ErrorBox error={error} />
      ) : items(data).length ? (
        <div className="linear-record-list">
          {items(data).map((s) => (
            <div className="linear-section" key={s.id}>
              <div className="row between">
                <h3>
                  {s.candidate?.alias || s.candidate_alias || "Специалист"}
                </h3>
                <Badge>
                  {s.content_redacted
                    ? "Содержание закрыто"
                    : s.result?.status || "На проверке"}
                </Badge>
              </div>
              {s.content_redacted || s.private_content_available === false ? (
                <Notice tone="amber">
                  {s.privacy_reason === "company_blocked"
                    ? "Кандидат заблокировал компанию. Ответ и его личная оценка недоступны; повторная оценка закрыта."
                    : "Кандидат отозвал согласие на обработку. Ответ и его личная оценка недоступны; повторная оценка закрыта."}
                </Notice>
              ) : (
                <>
                  <pre
                    className="code-input"
                    style={{
                      minHeight: 0,
                      padding: 15,
                      whiteSpace: "pre-wrap",
                    }}
                  >
                    {typeof s.answer === "string"
                      ? s.answer
                      : JSON.stringify(s.answer, null, 2)}
                  </pre>
                  <form
                    className="form-stack"
                    onSubmit={async (e) => {
                      e.preventDefault();
                      setBusy(true);
                      setMutationError(undefined);
                      const f = new FormData(e.currentTarget);
                      try {
                        await post(
                          `/challenges/${challengeId}/submissions/${s.id}/review`,
                          {
                            score: Number(f.get("score")),
                            feedback: f.get("feedback"),
                          },
                        );
                        await reload();
                        notify("Оценка компании сохранена отдельно от грейда");
                      } catch (err) {
                        setMutationError(err);
                      } finally {
                        setBusy(false);
                      }
                    }}
                  >
                    <div className="form-grid">
                      <Field label="Оценка компании, 0–100">
                        <input
                          name="score"
                          type="number"
                          min={0}
                          max={100}
                          required
                          defaultValue={s.result?.score ?? 0}
                        />
                      </Field>
                      <Field label="Обратная связь">
                        <input
                          name="feedback"
                          required
                          maxLength={3000}
                          placeholder="Что получилось и что стоит улучшить"
                          defaultValue={s.result?.feedback || ""}
                        />
                      </Field>
                    </div>
                    <Button type="submit" variant="secondary" busy={busy}>
                      Сохранить оценку компании
                    </Button>
                  </form>
                </>
              )}
            </div>
          ))}
        </div>
      ) : (
        <Empty
          title="Решений пока нет"
          text="Они появятся после отправки ответа специалистами."
        />
      )}
      {mutationError !== undefined && (
        <div className="top-gap">
          <ErrorBox error={mutationError} />
        </div>
      )}
    </Modal>
  );
}
function ChallengeEditor({
  onClose,
  onSaved,
}: {
  onClose: () => void;
  onSaved: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  return (
    <Modal
      title="Новая задача команды"
      description="Учебный контекст на 5–10 минут. Решение не должно быть производственной работой."
      onClose={onClose}
    >
      <form
        className="form-stack"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError(undefined);
          const f = new FormData(e.currentTarget);
          try {
            await post("/challenges", {
              title: f.get("title"),
              description: f.get("description"),
              specialization: f.get("specialization"),
              skill: f.get("competency"),
              public_task: {},
            });
            onSaved();
          } catch (err) {
            setError(err);
          } finally {
            setBusy(false);
          }
        }}
      >
        <Field label="Название">
          <input
            name="title"
            required
            maxLength={160}
            placeholder="Найдите ошибку в расчёте метрики"
          />
        </Field>
        <Field label="Условие и формат ответа">
          <textarea
            name="description"
            required
            maxLength={6000}
            placeholder="Опишите учебные данные, задачу и что нужно вернуть."
          />
        </Field>
        <div className="form-grid">
          <Field label="Специализация">
            <select name="specialization">
              {specs.map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Компетенция">
            <input
              name="competency"
              required
              placeholder="SQL / анализ данных"
            />
          </Field>
        </div>
        <Notice tone="amber">
          Задача компании помечается отдельно. Субъективная оценка не меняет
          подтверждённый грейд.
        </Notice>
        {error !== undefined && <ErrorBox error={error} />}
        <Button type="submit" busy={busy}>
          Опубликовать задачу <Plus size={15} />
        </Button>
      </form>
    </Modal>
  );
}

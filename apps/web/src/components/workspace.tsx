"use client";
import { useState, useEffect, useCallback, useRef } from "react";
import Link from "next/link";
import { competencyLabel } from "@/lib/competency-label";
import { useRouter } from "next/navigation";
import {
  LayoutDashboard,
  ContactRound,
  UserRound,
  ClipboardCheck,
  History,
  Inbox,
  BriefcaseBusiness,
  FlaskConical,
  ShieldCheck,
  Building2,
  Search,
  Users,
  Layers,
  ChevronDown,
  ChevronRight,
  Bell,
  LogOut,
  Menu,
  X,
  Sparkles,
  ArrowRight,
  Plus,
  Target,
  CheckCircle2,
  LockKeyhole,
  Code2,
  ArrowUpRight,
  Webhook,
  Activity,
} from "lucide-react";
import {
  api,
  post,
  Me,
  Dict,
  Profile,
  items,
  setCSRF,
  money,
  date,
  specName,
  gradeName,
  statusName,
  evidenceLabel,
  evidenceScore,
} from "@/lib/api";
import {
  Brand,
  Avatar,
  Button,
  PageTitle,
  Loading,
  ErrorBox,
  Reveal,
  Badge,
  Tag,
  Notice,
  Modal,
  Toast,
  Empty,
  LinkAction,
  ScoreRing,
} from "./ui";
import {
  ProfileEditor,
  Passport,
  Privacy,
  AssessmentSetup,
  HistoryPage,
  passportCategoryProvenance,
} from "@/features/candidate";
import { CompanyEditor, Needs, Talent } from "@/features/employer";
import { Invitations, Jobs, Practice } from "@/features/hiring";
import { IdentityPrivacy, Quality, ATS } from "@/features/operations";
import { fspProvenance } from "@/lib/fsp-provenance";
export type WorkspaceContext = {
  me: Me;
  notify: (text: string) => void;
  refresh: () => void;
};
const candidateNav = [
  { id: "overview", label: "Мой обзор", icon: LayoutDashboard },
  { id: "passport", label: "Паспорт компетенций", icon: ContactRound },
  { id: "profile", label: "Мой профиль", icon: UserRound },
  { id: "assessment", label: "Подтверждение навыков", icon: ClipboardCheck },
  { id: "history", label: "История результатов", icon: History },
  { id: "invitations", label: "Предложения команд", icon: Inbox },
  { id: "jobs", label: "Вакансии", icon: BriefcaseBusiness },
  { id: "practice", label: "Практика", icon: FlaskConical },
  { id: "privacy", label: "Приватность", icon: ShieldCheck },
];
const employerNav = [
  { id: "overview", label: "Обзор команды", icon: LayoutDashboard },
  { id: "needs", label: "Потребности", icon: Target },
  { id: "talent", label: "Банк специалистов", icon: Users },
  { id: "matches", label: "Подборки", icon: Layers },
  { id: "invitations", label: "Приглашения", icon: Inbox },
  { id: "vacancies", label: "Вакансии и отклики", icon: BriefcaseBusiness },
  { id: "practice", label: "Задачи команды", icon: FlaskConical },
  { id: "company", label: "Профиль компании", icon: Building2 },
  { id: "ats", label: "Доставка в ATS", icon: Webhook },
  { id: "privacy", label: "Приватность", icon: ShieldCheck },
];
export function Workspace({ section }: { section: string }) {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState<unknown>();
  const [toast, setToast] = useState("");
  const [mobile, setMobile] = useState(false);
  const [smallScreen, setSmallScreen] = useState(false);
  const sidebarRef = useRef<HTMLElement>(null);
  const [notifications, setNotifications] = useState<Dict[] | null>(null);
  const [unread, setUnread] = useState(0);
  const [notificationError, setNotificationError] = useState<unknown>();
  const [notificationsLoading, setNotificationsLoading] = useState(false);
  const notificationsGeneration = useRef(0);
  const [version, setVersion] = useState(0);
  const notify = useCallback((text: string) => setToast(text), []);
  const refresh = useCallback(() => {
    void api<Me>("/auth/me").then(setMe).catch(setError);
    setVersion((v) => v + 1);
  }, []);
  useEffect(() => {
    if (!smallScreen || !mobile) return;
    const opener = document.activeElement as HTMLElement | null;
    const drawer = sidebarRef.current;
    const controls = () =>
      Array.from(
        drawer?.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), [tabindex="0"]',
        ) || [],
      ).filter((el) => el.getClientRects().length > 0);
    controls()[0]?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setMobile(false);
      }
      if (event.key !== "Tab") return;
      const nodes = controls();
      const first = nodes[0],
        last = nodes[nodes.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      if (opener?.isConnected) opener.focus();
    };
  }, [smallScreen, mobile]);
  useEffect(() => {
    api<Me>("/auth/me")
      .then((m) => {
        setCSRF(m.csrf_token);
        setMe(m);
        if (!m.email_verified)
          router.replace(`/verify?email=${encodeURIComponent(m.email)}`);
        else if (m.consent_processing === false && section !== "privacy")
          router.replace("/workspace/privacy");
      })
      .catch((e) => {
        if (e.status === 401) router.replace("/login");
        else setError(e);
      });
  }, [router]);
  useEffect(() => {
    setMobile(false);
  }, [section]);
  useEffect(() => {
    const media = window.matchMedia("(max-width:700px)");
    const update = () => {
      setSmallScreen(media.matches);
      if (!media.matches) setMobile(false);
    };
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  useEffect(() => {
    const expired = () => {
      setMe(null);
      router.replace("/login");
    };
    const consent = () => {
      void api<Me>("/auth/me").then(setMe).catch(setError);
      router.replace("/workspace/privacy");
    };
    window.addEventListener("vector:session-expired", expired);
    window.addEventListener("vector:consent-required", consent);
    return () => {
      window.removeEventListener("vector:session-expired", expired);
      window.removeEventListener("vector:consent-required", consent);
    };
  }, [router]);
  useEffect(() => {
    if (!me?.email_verified || me?.consent_processing === false) return;
    let poll: ReturnType<typeof setInterval> | undefined;
    const refreshUnread = (refreshDomain = false) =>
      api("/notifications")
        .then((d) => {
          setUnread(d.unread || 0);
          if (refreshDomain)
            window.dispatchEvent(new Event("vector:domain-updated"));
        })
        .catch(() => {});
    void refreshUnread();
    const events = new EventSource("/api/v1/events");
    events.addEventListener("notification", () => {
      void refreshUnread(true);
    });
    events.addEventListener("session-ended", () => {
      events.close();
      if (poll) clearInterval(poll);
      void api<Me>("/auth/me")
        .then((current) => {
          setMe(current);
          if (current.consent_processing === false)
            router.replace("/workspace/privacy");
        })
        .catch(() => window.dispatchEvent(new Event("vector:session-expired")));
    });
    events.onerror = () => {
      events.close();
      if (!poll) poll = setInterval(() => void refreshUnread(true), 30000);
    };
    return () => {
      events.close();
      if (poll) clearInterval(poll);
    };
  }, [me?.email_verified, me?.consent_processing]);
  const openNotifications = async () => {
    const request = ++notificationsGeneration.current;
    setNotifications([]);
    setNotificationsLoading(true);
    setNotificationError(undefined);
    try {
      const response = await api("/notifications");
      if (request !== notificationsGeneration.current) return;
      setNotifications(items(response));
      await post("/notifications/read", { all: true });
      if (request === notificationsGeneration.current) setUnread(0);
    } catch (e) {
      if (request === notificationsGeneration.current) setNotificationError(e);
    } finally {
      if (request === notificationsGeneration.current)
        setNotificationsLoading(false);
    }
  };
  useEffect(
    () => () => {
      notificationsGeneration.current++;
    },
    [],
  );
  if (error !== undefined)
    return (
      <div className="center-page">
        <Brand />
        <ErrorBox error={error} retry={() => window.location.reload()} />
      </div>
    );
  if (!me) return <Loading label="Открываем твоё пространство" />;
  const nav = [
    ...(me.role === "employer" ? employerNav : candidateNav),
    ...(me.email.endsWith("@vector.local")
      ? [{ id: "quality", label: "Качество стенда", icon: Activity }]
      : []),
  ];
  const label =
    nav.find((n) => n.id === section)?.label || "Рабочее пространство";
  const ctx = { me, notify, refresh };
  return (
    <div className="workspace vector-workspace">
      {mobile && (
        <div
          className="sidebar-overlay"
          aria-hidden="true"
          onClick={() => setMobile(false)}
        />
      )}
      <aside
        ref={sidebarRef}
        id="workspace-navigation"
        className={`sidebar ${mobile ? "open" : ""}`}
        inert={smallScreen && !mobile ? true : undefined}
        aria-hidden={smallScreen && !mobile ? true : undefined}
      >
        <button
          className="icon-button sidebar-dismiss"
          aria-label="Закрыть меню"
          onClick={() => setMobile(false)}
        >
          <X size={18} />
        </button>
        <Brand />
        <div className="workspace-switch">
          <span className="purple-icon">
            {me.role === "employer" ? (
              <Building2 size={18} />
            ) : (
              <UserRound size={18} />
            )}
          </span>
          <div>
            {me.role === "employer" ? "Рабочая область" : "Моё пространство"}
            <small>
              {me.role === "employer" ? "Работодатель" : "Специалист"}
            </small>
          </div>
        </div>
        <div className="nav-group-label">
          {me.role === "employer" ? "Подбор и найм" : "Карьера и навыки"}
        </div>
        <nav className="sidebar-nav" aria-label="Рабочее пространство">
          {nav.map((n) => (
            <Link
              href={`/workspace/${n.id}`}
              key={n.id}
              className={section === n.id ? "active" : ""}
              aria-current={section === n.id ? "page" : undefined}
            >
              <n.icon />
              {n.label}
            </Link>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="sidebar-environment">
            <span className="live-dot" /> Локальная демонстрация
          </div>
          <div className="sidebar-user">
            <Avatar name={me.name} />
            <div>
              <strong title={me.name}>{me.name}</strong>
              <small title={me.email}>{me.email}</small>
            </div>
            <button
              className="icon-button"
              aria-label="Выйти"
              onClick={async () => {
                try {
                  await post("/auth/logout");
                  router.push("/login");
                } catch (e) {
                  setError(e);
                }
              }}
            >
              <LogOut size={15} />
            </button>
          </div>
        </div>
      </aside>
      <div
        className="workspace-surface"
        inert={smallScreen && mobile ? true : undefined}
      >
        <header className="topbar">
          <button
            className="icon-button mobile-menu"
            onClick={() => setMobile(!mobile)}
            aria-label={mobile ? "Закрыть меню" : "Открыть меню"}
            aria-expanded={mobile}
            aria-controls="workspace-navigation"
          >
            <Menu size={20} />
          </button>
          <div className="breadcrumb">
            <span>
              {me.role === "employer" ? "Команда" : "Моё пространство"}
            </span>
            <ChevronRight size={11} />
            <span>{label}</span>
          </div>
          <div className="topbar-right">
            <span className="local-label">
              <span className="live-dot" />
              Локальная демонстрация
            </span>
            <button
              className={`icon-button notification-button ${unread ? "unread" : ""}`}
              onClick={() => void openNotifications()}
              aria-label="Уведомления"
            >
              <Bell size={18} />
            </button>
            <Avatar size="small" name={me.name} />
          </div>
        </header>
        <main className="workspace-content" key={`${section}-${version}`}>
          <Reveal>
            {me.consent_processing === false ? (
              <IdentityPrivacy {...ctx} />
            ) : (
              renderSection(section, ctx)
            )}
          </Reveal>
        </main>
      </div>
      {toast && <Toast message={toast} onClose={() => setToast("")} />}{" "}
      {notifications !== null && (
        <Modal
          title="Уведомления"
          description="Обновления профиля, результатов и предложений."
          onClose={() => {
            notificationsGeneration.current++;
            setNotifications(null);
          }}
        >
          {notificationError !== undefined && (
            <ErrorBox error={notificationError} />
          )}
          <div className="notification-list">
            {notificationsLoading ? (
              <Loading label="Загружаем уведомления" />
            ) : notifications.length ? (
              notifications.map((n) => (
                <div className="notification-item" key={n.id}>
                  <strong>{n.title || n.type}</strong>
                  <p>{n.message || n.body}</p>
                  <small>{date(n.created_at)}</small>
                </div>
              ))
            ) : (
              <Empty
                title="Пока всё спокойно"
                text="Новые результаты и ответы появятся здесь."
              />
            )}
          </div>
        </Modal>
      )}
    </div>
  );
}
function renderSection(section: string, ctx: WorkspaceContext) {
  const employer = ctx.me.role === "employer";
  switch (section) {
    case "overview":
      return <Overview {...ctx} />;
    case "profile":
      return employer ? <CompanyEditor {...ctx} /> : <ProfileEditor {...ctx} />;
    case "passport":
      return <Passport {...ctx} />;
    case "assessment":
      return <AssessmentSetup {...ctx} />;
    case "history":
      return <HistoryPage {...ctx} />;
    case "privacy":
      return employer ? <IdentityPrivacy {...ctx} /> : <Privacy {...ctx} />;
    case "quality":
      return <Quality {...ctx} />;
    case "ats":
      return <ATS {...ctx} />;
    case "company":
      return <CompanyEditor {...ctx} />;
    case "needs":
      return <Needs {...ctx} />;
    case "talent":
      return <Talent {...ctx} />;
    case "matches":
      return <Talent {...ctx} saved />;
    case "invitations":
      return <Invitations {...ctx} />;
    case "jobs":
    case "vacancies":
      return <Jobs {...ctx} />;
    case "practice":
      return <Practice {...ctx} />;
    default:
      return (
        <Empty
          title="Такого раздела нет"
          text="Вернись к обзору рабочего пространства."
          action={
            <Link href="/workspace/overview" className="button primary">
              Открыть обзор
            </Link>
          }
        />
      );
  }
}
function Overview(ctx: WorkspaceContext) {
  const [data, setData] = useState<Dict | null>(null);
  const [error, setError] = useState<unknown>();
  const employer = ctx.me.role === "employer";
  useEffect(() => {
    api(`/${employer ? "employer" : "candidate"}/dashboard`)
      .then(setData)
      .catch(setError);
  }, [employer]);
  if (error !== undefined) return <ErrorBox error={error} />;
  if (!data) return <Loading />;
  const stats = data.stats || {};
  const profile = data.profile as Profile;
  return (
    <>
      <PageTitle
        eyebrow={new Date().toLocaleDateString("ru-RU", {
          weekday: "long",
          day: "numeric",
          month: "long",
        })}
        title={`${employer ? "Здравствуйте" : "Привет"}, ${ctx.me.name.split(" ")[0]}${employer ? "" : "."}`}
        description={
          employer
            ? "Найти подходящего человека проще, когда видны основания."
            : "Здесь твои навыки превращаются в новые возможности."
        }
        action={
          <Link
            href={employer ? "/workspace/needs" : "/workspace/passport"}
            className="button secondary"
          >
            {employer ? <Plus size={15} /> : <ArrowUpRight size={15} />}{" "}
            {employer ? "Новая потребность" : "Мой паспорт"}
          </Link>
        }
      />
      {employer ? (
        <EmployerOverview data={data} />
      ) : (
        <CandidateOverview profile={profile} data={data} />
      )}
      <div className="metrics">
        {(employer
          ? [
              {
                label: "Опубликованных специалистов",
                value: stats.candidates,
                icon: Users,
              },
              {
                label: "Потребностей команды",
                value: stats.needs,
                icon: Target,
              },
              {
                label: "Отправленных приглашений",
                value: stats.invitations,
                icon: Inbox,
              },
              {
                label: "Принятых предложений",
                value: stats.accepted,
                icon: CheckCircle2,
              },
            ]
          : [
              {
                label: "Свидетельств в паспорте",
                value: stats.confirmed_competencies,
                icon: ShieldCheck,
              },
              {
                label: "Попыток экзамена",
                value: stats.assessments,
                icon: ClipboardCheck,
              },
              {
                label: "Предложений команд",
                value: stats.invitations,
                icon: Inbox,
              },
              {
                label: "Ожидают твоего ответа",
                value: stats.active_invitations,
                icon: BriefcaseBusiness,
              },
            ]
        ).map((m) => (
          <div className="metric" key={m.label}>
            <div>
              <small>{m.label}</small>
              <strong>{m.value ?? 0}</strong>
            </div>
            <span>
              <m.icon />
            </span>
          </div>
        ))}
      </div>
      <div className="grid-two linear-overview-sections">
        {employer ? (
          <div className="panel">
            <div className="panel-header">
              <h2>Потребности команды</h2>
              <LinkAction href="/workspace/needs">Все потребности</LinkAction>
            </div>
            {data.needs?.length ? (
              data.needs.slice(0, 3).map((n: Dict) => (
                <div className="list-row" key={n.id}>
                  <div>
                    <strong>{n.title}</strong>
                    <small>
                      {specName(n.specialization)} · {gradeName(n.grade)}
                    </small>
                  </div>
                  <Link
                    className="link-action"
                    href={`/workspace/matches?need=${n.id}`}
                  >
                    Подобрать <ArrowRight size={14} />
                  </Link>
                </div>
              ))
            ) : (
              <Empty
                title="С какой задачи начнём?"
                text="Опиши потребность команды, чтобы получить первую подборку."
                action={
                  <Link href="/workspace/needs" className="button primary">
                    Создать потребность
                  </Link>
                }
              />
            )}
          </div>
        ) : (
          <DashboardPassport profile={profile} />
        )}
        <div className="panel">
          <div className="panel-header">
            <h2>
              {employer ? "Последние приглашения" : "Предложения для тебя"}
            </h2>
            <LinkAction href="/workspace/invitations">Все</LinkAction>
          </div>
          {(employer ? data.recent_invitations : data.invitations)?.length ? (
            (employer ? data.recent_invitations : data.invitations)
              .slice(0, 3)
              .map((i: Dict) => (
                <div className="invitation-card" key={i.id}>
                  <div className="invitation-card-head">
                    <span className="company-symbol">
                      {String(i.company?.name || i.company_name || "В").slice(
                        0,
                        1,
                      )}
                    </span>
                    <div>
                      <h3>{i.company?.name || i.company_name || "Команда"}</h3>
                      <small>{date(i.created_at)}</small>
                    </div>
                    <Badge tone={i.status === "accepted" ? "green" : "purple"}>
                      {statusName(i.status)}
                    </Badge>
                  </div>
                  <h4>{i.title}</h4>
                  <p>
                    {money(i.salary_from)} — {money(i.salary_to)} ₽
                  </p>
                  <div className="invitation-card-bottom">
                    <span>
                      {(
                        {
                          remote: "Удалённо",
                          hybrid: "Гибрид",
                          office: "В офисе",
                          any: "Любой формат",
                        } as Record<string, string>
                      )[i.work_format] || "Формат не указан"}
                    </span>
                    <LinkAction href="/workspace/invitations">
                      Подробнее
                    </LinkAction>
                  </div>
                </div>
              ))
          ) : (
            <Empty
              icon="spark"
              title={
                employer ? "Новые связи впереди" : "Твоя команда ещё впереди"
              }
              text={
                employer
                  ? "Выбери специалиста в подборке и отправь персональное предложение."
                  : "Подтверди навыки и включи публикацию. Команды смогут находить твой профиль."
              }
            />
          )}
        </div>
      </div>
      <div className="grid-equal top-gap linear-overview-sections">
        <div className="panel">
          <div className="panel-header">
            <h2>{employer ? "Как работает подбор" : "Связь с ФСП"}</h2>
            <ShieldCheck size={17} className="muted" />
          </div>
          {employer ? (
            <p className="no-margin" style={{ fontSize: 12, lineHeight: 1.8 }}>
              Специализация и подтверждённый грейд определяют допуск. Покрытие
              компетенций, результат экзамена и условия формируют индекс
              соответствия. Вклад каждого фактора виден в профиле.
            </p>
          ) : (
            <>
              <div className="fsp-row">
                <span className="fsp-symbol">ФСП</span>
                <div>
                  <strong>
                    {profile?.fsp?.status === "sync_ok"
                      ? "Достижения связаны"
                      : "Достижения дополняют твой паспорт"}
                  </strong>
                  <small>
                    {profile?.fsp?.status === "sync_ok"
                      ? fspProvenance(profile.fsp).label
                      : "Участие в ФСП необязательно для поиска работы"}
                  </small>
                </div>
                <Link
                  href="/workspace/passport"
                  className="icon-button"
                  aria-label="Открыть связь с ФСП в паспорте"
                >
                  <ChevronRight size={16} />
                </Link>
              </div>
            </>
          )}
        </div>
        <div className="panel">
          <div className="panel-header">
            <h2>Контроль остаётся у тебя</h2>
            <LockKeyhole size={17} className="muted" />
          </div>
          <p style={{ fontSize: 12, lineHeight: 1.8, margin: 0 }}>
            {employer
              ? "До разрешения кандидата доступен безопасный профиль. Контакты открываются только вашей компании при принятии приглашения или самостоятельном отклике."
              : "Публикация карточки и доступ к контактам управляются отдельно. Ты можешь скрыть профиль или отозвать доступ конкретной компании."}
          </p>
          {!employer && (
            <div className="top-gap">
              <LinkAction href="/workspace/privacy">
                Настройки приватности
              </LinkAction>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
function CandidateOverview({
  profile,
  data,
}: {
  profile: Profile;
  data: Dict;
}) {
  const confirmed = !!profile?.confirmed_grade;
  const published = profile?.published;
  return (
    <div className="next-step">
      <div className="step-art">
        {confirmed ? <ShieldCheck size={28} /> : <Code2 size={28} />}
      </div>
      <div>
        <h2>
          {confirmed
            ? published
              ? "Твой профиль открыт для возможностей"
              : "Категория есть в паспорте. Покажи её командам."
            : "Покажи навыки — открой новые возможности"}
        </h2>
        <p>
          {confirmed
            ? published
              ? "Работодатели видят основания навыков. Контакты остаются скрыты до твоего решения."
              : "Включи публикацию безопасного профиля, чтобы команды могли тебя найти."
            : "Выбери специализацию и пройди практический экзамен. Результат станет основой твоего паспорта."}
        </p>
      </div>
      <Link
        className="button primary"
        href={confirmed ? "/workspace/privacy" : "/workspace/assessment"}
      >
        {confirmed ? "Управлять публикацией" : "Подтвердить навыки"}
        <ArrowRight size={15} />
      </Link>
    </div>
  );
}
function EmployerOverview({ data }: { data: Dict }) {
  return (
    <div className="next-step">
      <div className="step-art">
        <Target size={28} />
      </div>
      <div>
        <h2>Какие навыки нужны вашей команде?</h2>
        <p>
          Опишите контекст, сравните подтверждения и пригласите подходящего
          специалиста.
        </p>
      </div>
      <Link className="button primary" href="/workspace/needs">
        Создать потребность
        <ArrowRight size={15} />
      </Link>
    </div>
  );
}
function DashboardPassport({ profile }: { profile: Profile }) {
  const competencies = (profile?.evidence || []).slice(0, 4);
  const provenance = passportCategoryProvenance(
    profile,
    profile?.evidence || [],
  );
  return (
    <div className="panel dashboard-passport">
      <div className="panel-header">
        <h2>Мой паспорт компетенций</h2>
        <span className="passport-id">
          <ShieldCheck size={12} /> {profile?.id?.slice(0, 8).toUpperCase()}
        </span>
      </div>
      <div className="passport-grade-row">
        <div>
          <h3>
            {profile?.confirmed_grade
              ? `${gradeName(profile.confirmed_grade)}`
              : "Твой уровень — впереди"}
          </h3>
          <p>{specName(profile?.specialization)}</p>
        </div>
        <Badge tone={provenance.tone}>
          {profile?.confirmed_grade ? (
            <>
              <ShieldCheck size={11} />
              {provenance.label}
            </>
          ) : (
            "Ещё не подтверждён"
          )}
        </Badge>
      </div>
      {competencies.length ? (
        <div className="linear-source-list">
          {competencies.map((c: Dict, i: number) => (
            <div key={c.id || i}>
              <div className="competency-bar-top">
                <span>{competencyLabel(c.label || c.competency || c.skill)}</span>
                <strong>
                  {evidenceScore(c) !== null
                    ? `${Math.round(evidenceScore(c)!)} / 100`
                    : "Не измерено"}
                </strong>
              </div>
              <small className="evidence-note">{evidenceLabel(c)}</small>
            </div>
          ))}
        </div>
      ) : (
        <div className="notice">
          <ShieldCheck size={17} />
          <span>
            Заявленные навыки появятся здесь с подтверждениями после экзамена.
          </span>
        </div>
      )}
      <div className="passport-meta">
        <span>
          {profile?.category
            ? `${specName(profile.specialization)} · ${gradeName(profile.confirmed_grade)}`
            : "Категория пока не присвоена"}
        </span>
        <LinkAction href="/workspace/passport">Открыть паспорт</LinkAction>
      </div>
    </div>
  );
}

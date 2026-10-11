"use client";
import { useEffect, useState, useRef } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  ArrowRight,
  ArrowLeft,
  Eye,
  EyeOff,
  ShieldCheck,
  Mail,
  CheckCircle2,
} from "lucide-react";
import { api, post, Me, items, Dict } from "@/lib/api";
import { Button, Field, ErrorBox, Loading, Notice } from "./ui";
import { AuthFrame } from "./auth-visual";
export function AuthPage({ register = false }: { register?: boolean }) {
  const router = useRouter();
  const params = useSearchParams();
  const [role, setRole] = useState<"candidate" | "employer">(
    params.get("role") === "employer" ? "employer" : "candidate",
  );
  const [stage, setStage] = useState<"email" | "details">("email");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [success, setSuccess] = useState(false);
  const [delivery, setDelivery] = useState("");
  const [localMailbox, setLocalMailbox] = useState(false);
  const [email, setEmail] = useState("");
  const detailsHeading = useRef<HTMLHeadingElement>(null);
  const emailInput = useRef<HTMLInputElement>(null);
  const previousStage = useRef(stage);
  useEffect(() => {
    if (previousStage.current === stage) return;
    previousStage.current = stage;
    if (stage === "details") detailsHeading.current?.focus();
    else emailInput.current?.focus();
  }, [stage]);
  const submit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (busy) return;
    if (register && stage === "email") {
      setError(undefined);
      setStage("details");
      return;
    }
    setBusy(true);
    setError(undefined);
    const form = new FormData(e.currentTarget);
    try {
      if (register) {
        const result = await post<Dict>("/auth/register", {
          name: form.get("name"),
          email,
          password: form.get("password"),
          role,
          consent_processing: form.get("consent") === "on",
        });
        setDelivery(String(result.delivery || ""));
        if (result.delivery === "local_mailbox") {
          setLocalMailbox(true);
        } else {
          try {
            await api(`/auth/demo-mailbox?email=${encodeURIComponent(email)}`);
            setLocalMailbox(true);
          } catch {
            setLocalMailbox(false);
          }
        }
        setSuccess(true);
      } else {
        const me = await post<Me>("/auth/login", {
          email: form.get("email"),
          password: form.get("password"),
        });
        router.push(
          me.email_verified
            ? "/workspace/overview"
            : `/verify?email=${encodeURIComponent(me.email)}`,
        );
      }
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };
  return (
    <AuthFrame role={role}>
      <div
        className="auth-card vector-auth-content"
        key={success ? "success" : stage}
      >
        {success ? (
          <>
            <span className="vector-auth-state-icon">
              <Mail size={22} aria-hidden="true" />
            </span>
            <h1 className="vector-auth-heading">Подтверди свою почту</h1>
            <p>
              Аккаунт для <strong>{email}</strong> создан.
            </p>
            <p className="auth-note">
              {delivery === "local_mailbox"
                ? "Письмо сохранено в локальной демопочте. Отправка во внешний ящик не выполняется."
                : delivery === "queued_smtp"
                  ? "Письмо поставлено в очередь SMTP. Доставка ещё не подтверждена."
                  : delivery === "pending_transport"
                    ? "Письмо подготовлено, но почтовый транспорт не настроен. Для подтверждения нужен настроенный способ доставки."
                    : "Для начала работы подтверди адрес по ссылке в письме."}
            </p>
            {localMailbox && (
              <Link
                className="button primary full"
                href={`/demo/inbox?email=${encodeURIComponent(email)}`}
              >
                Открыть локальную демопочту <ArrowRight size={16} />
              </Link>
            )}
            <Link href="/login" className="link-action">
              Перейти ко входу
            </Link>
          </>
        ) : (
          <>
            <h1
              className="vector-auth-heading"
              id="auth-heading"
              ref={detailsHeading}
              tabIndex={-1}
            >
              {register
                ? stage === "email"
                  ? "Твоя электронная почта"
                  : "Создай свой аккаунт"
                : "Войти в ФСП Вектор"}
            </h1>
            <p className="vector-auth-description">
              {register
                ? stage === "email"
                  ? "Начнём с адреса, к которому у тебя есть доступ."
                  : "Осталось несколько деталей, чтобы начать работу."
                : "Продолжи работу с профилем, навыками и предложениями."}
            </p>
            {register && stage === "details" && (
              <button
                type="button"
                className="vector-auth-edit-email"
                disabled={busy}
                onClick={() => setStage("email")}
                aria-label={`Изменить электронную почту ${email}`}
              >
                <ArrowLeft size={14} aria-hidden="true" /> {email}{" "}
                <span>Изменить</span>
              </button>
            )}
            <form
              onSubmit={submit}
              className={`form-stack${register && stage === "email" ? " vector-auth-email-step" : ""}`}
              aria-labelledby="auth-heading"
            >
              {(!register || stage === "email") && (
                <label className="field">
                  <span>Электронная почта</span>
                  <input
                    ref={emailInput}
                    name="email"
                    type="email"
                    autoComplete="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@company.ru"
                    disabled={busy}
                  />
                </label>
              )}
              {register && stage === "details" && (
                <>
                  <fieldset className="role-switch" disabled={busy}>
                    <legend className="sr-only">Тип аккаунта</legend>
                    <button
                      type="button"
                      aria-pressed={role === "candidate"}
                      className={role === "candidate" ? "active" : ""}
                      onClick={() => setRole("candidate")}
                    >
                      Я специалист
                    </button>
                    <button
                      type="button"
                      aria-pressed={role === "employer"}
                      className={role === "employer" ? "active" : ""}
                      onClick={() => setRole("employer")}
                    >
                      Я работодатель
                    </button>
                  </fieldset>
                  <Field label="Как тебя зовут">
                    <input
                      name="name"
                      autoComplete="name"
                      required
                      minLength={2}
                      maxLength={100}
                      placeholder="Имя и фамилия"
                      disabled={busy}
                    />
                  </Field>
                </>
              )}
              {(!register || stage === "details") && (
                <div className="field">
                  <label htmlFor="auth-password">Пароль</label>
                  <div className="password-input">
                    <input
                      id="auth-password"
                      name="password"
                      type={show ? "text" : "password"}
                      autoComplete={
                        register ? "new-password" : "current-password"
                      }
                      required
                      minLength={register ? 12 : 1}
                      placeholder="Введи пароль"
                      disabled={busy}
                      aria-describedby={
                        register ? "password-guidance" : undefined
                      }
                    />
                    <button
                      type="button"
                      onClick={() => setShow(!show)}
                      aria-label={show ? "Скрыть пароль" : "Показать пароль"}
                      aria-pressed={show}
                      disabled={busy}
                    >
                      {show ? <EyeOff size={16} /> : <Eye size={16} />}
                    </button>
                  </div>
                  {register && (
                    <small id="password-guidance">
                      Не меньше 12 символов. Используй буквы и цифры.
                    </small>
                  )}
                </div>
              )}
              {register && stage === "details" && (
                <label className="check-label">
                  <input
                    type="checkbox"
                    name="consent"
                    required
                    disabled={busy}
                  />
                  <span>
                    Даю отдельное согласие на обработку данных для работы
                    платформы. Публикацию профиля включу отдельно.
                  </span>
                </label>
              )}
              {error !== undefined && <ErrorBox error={error} />}
              <Button busy={busy} type="submit" className="full">
                {register
                  ? stage === "email"
                    ? "Продолжить с почтой"
                    : "Создать аккаунт"
                  : "Войти"}
              </Button>
            </form>
            {register && stage === "email" && (
              <p className="auth-note">
                На следующем шаге — пароль и отдельное согласие на обработку
                данных.
              </p>
            )}
            <p className="auth-switch">
              {register ? "Уже есть аккаунт?" : "Первый раз здесь?"}{" "}
              <Link href={register ? "/login" : "/register"}>
                {register ? "Войти" : "Создать аккаунт"}
              </Link>
            </p>
            {!register && (
              <details className="demo-credentials">
                <summary>Локальные демоаккаунты</summary>
                <p>
                  Специалист: candidate@vector.local
                  <br />
                  Работодатель: employer@vector.local
                  <br />
                  Пароль: VectorDemo2026!
                </p>
                <small>Все профили и компании в демонстрации вымышлены.</small>
              </details>
            )}
            {!register && <OIDCLogin role={role} />}
          </>
        )}
      </div>
    </AuthFrame>
  );
}
export function Verification() {
  const params = useSearchParams();
  const token = params.get("token");
  const startedToken = useRef<string | null>(null);
  const email = params.get("email") || "";
  const [state, setState] = useState("loading");
  const [error, setError] = useState<unknown>();
  useEffect(() => {
    if (!token) {
      setState("pending");
      return;
    }
    if (startedToken.current === token) return;
    startedToken.current = token;
    api(`/auth/verify?token=${encodeURIComponent(token)}`)
      .then(() => setState("success"))
      .catch((e) => {
        setError(e);
        setState("error");
      });
  }, [token]);
  return (
    <AuthFrame>
      <div className="auth-card vector-auth-content vector-auth-status">
        {state === "loading" ? (
          <Loading label="Подтверждаем почту" />
        ) : state === "success" ? (
          <>
            <CheckCircle2 className="large-icon green" />
            <h1 className="vector-auth-heading">Почта подтверждена</h1>
            <p>Теперь можно открыть рабочее пространство.</p>
            <Link className="button primary" href="/login">
              Войти в аккаунт <ArrowRight size={17} />
            </Link>
          </>
        ) : (
          <>
            <Mail className="large-icon purple" />
            <h1 className="vector-auth-heading">
              {state === "error"
                ? "Не удалось подтвердить почту"
                : "Проверь свою почту"}
            </h1>
            <p>
              {state === "error"
                ? "Открой письмо и проверь ссылку подтверждения. Если адрес уже подтверждён, перейди ко входу."
                : "Для доступа к профилю и предложениям нужно подтвердить email."}
            </p>
            {error !== undefined && <ErrorBox error={error} />}
            <ResendVerification />
            <Link
              className="button primary"
              href={`/demo/inbox?email=${encodeURIComponent(email)}`}
            >
              Открыть локальную демопочту
            </Link>
            <Link href="/login" className="link-action">
              Вернуться ко входу
            </Link>
          </>
        )}
      </div>
    </AuthFrame>
  );
}
function ResendVerification() {
  const [account, setAccount] = useState<Me | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [delivery, setDelivery] = useState("");
  const sending = useRef(false);
  useEffect(() => {
    let active = true;
    api<Me>("/auth/me")
      .then((me) => {
        if (active && !me.email_verified) setAccount(me);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);
  const resend = async () => {
    if (!account || sending.current) return;
    sending.current = true;
    setBusy(true);
    setError(undefined);
    setDelivery("");
    try {
      const response = await post("/auth/resend-verification");
      setDelivery(String(response.delivery || "pending_transport"));
    } catch (e) {
      setError(e);
    } finally {
      sending.current = false;
      setBusy(false);
    }
  };
  if (!account) return null;
  return (
    <div className="form-stack bottom-gap">
      <p className="auth-note">
        Новое письмо будет подготовлено для {account.email}.
      </p>
      <Button variant="secondary" busy={busy} onClick={() => void resend()}>
        Запросить новое письмо
      </Button>
      {delivery && (
        <p className="auth-note" role="status">
          {delivery === "local_mailbox"
            ? "Новое письмо подготовлено. Оно доступно в локальной демопочте; внешняя доставка не подтверждается этим сообщением."
            : "Новое письмо подготовлено для почтового транспорта. Его доставка ещё не подтверждена."}
        </p>
      )}
      {error !== undefined && <ErrorBox error={error} />}
    </div>
  );
}
export function DemoInbox() {
  const params = useSearchParams();
  const [email, setEmail] = useState(params.get("email") || "");
  const [messages, setMessages] = useState<Dict[] | null>(null);
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  const requestSerial = useRef(0);
  const load = async () => {
    const serial = ++requestSerial.current;
    setError(undefined);
    setMessages(null);
    setBusy(true);
    try {
      const result = items(
        await api(`/auth/demo-mailbox?email=${encodeURIComponent(email)}`),
      );
      if (serial === requestSerial.current) setMessages(result);
    } catch (e) {
      if (serial === requestSerial.current) setError(e);
    } finally {
      if (serial === requestSerial.current) setBusy(false);
    }
  };
  useEffect(() => {
    if (params.get("email")) void load();
  }, []);
  return (
    <AuthFrame inbox>
      <div className="auth-card vector-auth-content vector-auth-mailbox">
        <h1 className="vector-auth-heading">Локальная демопочта</h1>
        <Notice>
          Письма доступны только в режиме локальной демонстрации. Этот ящик не
          предназначен для реальных персональных данных.
        </Notice>
        <form
          className="inline-form"
          onSubmit={(e) => {
            e.preventDefault();
            void load();
          }}
        >
          <input
            type="email"
            required
            aria-label="Адрес аккаунта"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="Адрес аккаунта"
            disabled={busy}
          />
          <Button type="submit" busy={busy}>
            Найти письма
          </Button>
        </form>
        {error !== undefined && <ErrorBox error={error} />}
        {busy && <Loading label="Ищем письма" />}
        <div className="mail-list">
          {messages?.map((m) => (
            <div key={m.id} className="mail-item">
              <BadgeMail />
              <div>
                <strong>{m.subject}</strong>
                <p>{m.body}</p>
                {m.verification_url && (
                  <Link
                    className="button secondary"
                    href={verificationPath(m.verification_url)}
                  >
                    Подтвердить почту <ArrowRight size={16} />
                  </Link>
                )}
              </div>
            </div>
          ))}
          {messages?.length === 0 && (
            <p className="muted">
              Писем пока нет. Проверь адрес или создай аккаунт.
            </p>
          )}
        </div>
        <Link className="link-action" href="/login">
          Вернуться ко входу
        </Link>
      </div>
    </AuthFrame>
  );
}
function verificationPath(value: string) {
  try {
    const url = new URL(value, "http://localhost");
    return `/verify${url.search}`;
  } catch {
    return value;
  }
}
function BadgeMail() {
  return (
    <span className="purple-icon">
      <Mail size={20} />
    </span>
  );
}

function OIDCLogin({ role }: { role: "candidate" | "employer" }) {
  const [enabled, setEnabled] = useState(false);
  useEffect(() => {
    api("/auth/oidc/status")
      .then((s) => setEnabled(!!s.enabled))
      .catch(() => setEnabled(false));
  }, []);
  return enabled ? (
    <div className="oidc-entry">
      <a
        className="button secondary full"
        href={`/api/v1/auth/oidc/login?role=${role}`}
      >
        <ShieldCheck size={15} /> Единый вход
      </a>
      <small>
        Локальная демонстрация identity. Это не вход в реальную ФСП.
      </small>
    </div>
  ) : null;
}

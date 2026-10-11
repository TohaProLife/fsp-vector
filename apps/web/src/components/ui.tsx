"use client";
import { useEffect, useRef } from "react";
import { motion, useReducedMotion } from "motion/react";
import {
  ArrowRight,
  Check,
  CheckCircle2,
  ChevronRight,
  LoaderCircle,
  ShieldCheck,
  Sparkles,
  X,
  AlertCircle,
  Search,
} from "lucide-react";
import Link from "next/link";
export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <Link href="/" className="brand" aria-label="ФСП Вектор — главная">
      <svg className="brand-mark" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M2 3h5.5L13 14.5 7.5 23 2 11.5V3Z" fill="currentColor" />
        <path d="M10 1h12v12l-4-4-8 12-3.5-7L14 5l-4-4Z" fill="currentColor" />
      </svg>
      {!compact && (
        <span>
          <strong>ФСП Вектор</strong>
        </span>
      )}
    </Link>
  );
}
export function Reveal({
  children,
  className = "",
  delay = 0,
}: {
  children: React.ReactNode;
  className?: string;
  delay?: number;
}) {
  const reduced = useReducedMotion();
  return (
    <motion.div
      className={className}
      initial={reduced ? false : { opacity: 1, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        duration: reduced ? 0 : 0.16,
        delay: reduced ? 0 : delay,
        ease: [0.16, 1, 0.3, 1],
      }}
    >
      {children}
    </motion.div>
  );
}
export function Button({
  children,
  variant = "primary",
  busy = false,
  className = "",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  busy?: boolean;
}) {
  return (
    <button
      {...props}
      className={`button ${variant} ${className}`}
      disabled={props.disabled || busy}
    >
      {busy ? <LoaderCircle size={16} className="spin" /> : null}
      {children}
    </button>
  );
}
export function Badge({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: "neutral" | "green" | "purple" | "amber" | "red";
}) {
  return <span className={`badge ${tone}`}>{children}</span>;
}
export function Tag({
  children,
  verified = false,
}: {
  children: React.ReactNode;
  verified?: boolean;
}) {
  return (
    <span className={`tag ${verified ? "verified" : ""}`}>
      {verified && <Check size={12} />} {children}
    </span>
  );
}
export function Field({
  label,
  hint,
  children,
  error,
  group = false,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
  error?: string;
  group?: boolean;
}) {
  if (group)
    return (
      <fieldset className="field field-group">
        <legend>{label}</legend>
        {children}
        {error && <small className="field-error">{error}</small>}
        {hint && <small>{hint}</small>}
      </fieldset>
    );
  return (
    <label className="field">
      <span>{label}</span>
      {children}
      {error && <small className="field-error">{error}</small>}
      {hint && <small>{hint}</small>}
    </label>
  );
}
export function PageTitle({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="page-title">
      <div>
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {action}
    </div>
  );
}
export function Empty({
  title,
  text,
  action,
  icon = "search",
}: {
  title: string;
  text: string;
  action?: React.ReactNode;
  icon?: string;
}) {
  return (
    <div className="empty">
      <span className="empty-symbol">
        {icon === "check" ? (
          <ShieldCheck />
        ) : icon === "spark" ? (
          <Sparkles />
        ) : (
          <Search />
        )}
      </span>
      <h3>{title}</h3>
      <p>{text}</p>
      {action}
    </div>
  );
}
export function Loading({ label = "Загружаем данные" }: { label?: string }) {
  return (
    <div className="loading" role="status">
      <LoaderCircle className="spin" />
      <span>{label}</span>
    </div>
  );
}
export function ErrorBox({
  error,
  retry,
}: {
  error: unknown;
  retry?: () => void;
}) {
  return (
    <div className="error-box" role="alert">
      <AlertCircle size={20} />
      <div>
        <strong>Не удалось выполнить действие</strong>
        <p>{error instanceof Error ? error.message : String(error)}</p>
        {retry && <button onClick={retry}>Повторить</button>}
      </div>
    </div>
  );
}
export function Notice({
  children,
  tone = "purple",
}: {
  children: React.ReactNode;
  tone?: string;
}) {
  return (
    <div className={`notice ${tone}`}>
      <ShieldCheck size={18} />
      <div>{children}</div>
    </div>
  );
}
export function Modal({
  title,
  description,
  children,
  onClose,
  wide = false,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  const reduced = useReducedMotion();
  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement;
    const old = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    ref.current?.focus();
    const handler = (e: KeyboardEvent) => {
      const top = Array.from(document.querySelectorAll('[role="dialog"]')).at(
        -1,
      );
      if (top !== ref.current) return;
      if (e.key === "Escape") onCloseRef.current();
      if (e.key === "Tab" && ref.current) {
        const list = Array.from(
          ref.current.querySelectorAll<HTMLElement>(
            'button:not([disabled]),a,input,select,textarea,[tabindex="0"]',
          ),
        ).filter(
          (el) => el.getClientRects().length && !el.hasAttribute("disabled"),
        );
        const first = list[0],
          last = list[list.length - 1];
        if (
          document.activeElement === ref.current ||
          !ref.current.contains(document.activeElement)
        ) {
          e.preventDefault();
          (e.shiftKey ? last : first)?.focus();
        } else if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last?.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first?.focus();
        }
      }
    };
    document.addEventListener("keydown", handler);
    return () => {
      document.body.style.overflow = old;
      document.removeEventListener("keydown", handler);
      previous?.focus();
    };
  }, []);
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <motion.div
        ref={ref}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={`modal ${wide ? "wide" : ""}`}
        initial={reduced ? false : { opacity: 0, y: 6, scale: 0.995 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: reduced ? 0 : 0.18, ease: [0.16, 1, 0.3, 1] }}
      >
        <button
          className="icon-button close"
          onClick={onClose}
          aria-label="Закрыть"
        >
          <X />
        </button>
        <h2>{title}</h2>
        {description && <p className="muted">{description}</p>}
        {children}
      </motion.div>
    </div>
  );
}
export function Toast({
  message,
  onClose,
}: {
  message: string;
  onClose: () => void;
}) {
  useEffect(() => {
    const id = setTimeout(onClose, 5000);
    return () => clearTimeout(id);
  }, [message, onClose]);
  return (
    <div className="toast" role="status">
      <CheckCircle2 size={20} />
      {message}
      <button onClick={onClose} aria-label="Закрыть уведомление">
        <X size={16} />
      </button>
    </div>
  );
}
export function Avatar({
  name,
  size = "normal",
}: {
  name?: string;
  size?: string;
}) {
  const n = name || "Вектор";
  return (
    <span className={`avatar ${size}`}>
      {n
        .split(" ")
        .slice(0, 2)
        .map((x) => x[0])
        .join("")
        .toUpperCase()}
    </span>
  );
}
export function LinkAction({
  href,
  children,
}: {
  href: string;
  children: React.ReactNode;
}) {
  return (
    <Link className="link-action" href={href}>
      {children}
      <ArrowRight size={16} />
    </Link>
  );
}
export function ScoreRing({
  score,
  label = "индекс соответствия",
  small = false,
}: {
  score: number;
  label?: string;
  small?: boolean;
}) {
  const safe = Math.max(0, Math.min(100, Number(score) || 0));
  return (
    <div className={`score-inline ${small ? "small" : ""}`}>
      <div>
        <strong>
          {Math.round(safe)}
          <span>/100</span>
        </strong>
        {!small && <small>{label}</small>}
      </div>
    </div>
  );
}
export function ListRow({
  title,
  subtitle,
  end,
  href,
}: {
  title: string;
  subtitle?: string;
  end?: React.ReactNode;
  href?: string;
}) {
  const body = (
    <>
      <div>
        <strong>{title}</strong>
        {subtitle && <small>{subtitle}</small>}
      </div>
      <span>{end || <ChevronRight size={18} />}</span>
    </>
  );
  return href ? (
    <Link className="list-row" href={href}>
      {body}
    </Link>
  ) : (
    <div className="list-row">{body}</div>
  );
}

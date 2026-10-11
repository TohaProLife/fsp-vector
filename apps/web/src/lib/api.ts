export type Me = {
  id: string;
  name: string;
  email: string;
  role: "candidate" | "employer";
  email_verified: boolean;
  consent_processing?: boolean;
  csrf_token: string;
  candidate_id?: string;
  company_id?: string;
};
export type Dict = Record<string, any>;
export type Profile = Dict & {
  id: string;
  name: string;
  alias: string;
  title: string;
  bio: string;
  city: string;
  specialization: string;
  declared_grade: string;
  confirmed_grade?: string;
  category?: string;
  score?: number;
  skills: string[];
  preferences: Dict;
  published: boolean;
  fsp: Dict;
  history: Dict[];
  evidence?: Dict[];
};
export type Need = Dict & {
  id: string;
  title: string;
  description: string;
  specialization: string;
  grade: string;
  skills: string[];
  required_skills: string[];
  salary_from: number;
  salary_to: number;
  work_format: string;
  employment: string;
  team: string;
};
export type Attempt = Dict & {
  id: string;
  status: string;
  specialization: string;
  grade: string;
  expires_at: string;
  started_at: string;
  items: Dict[];
  answers: Record<string, unknown>;
  result?: Dict;
  policy: Dict;
};
let csrf = "";
let csrfRefresh: Promise<void> | null = null;
export function setCSRF(token: string) {
  csrf = token;
}
export class ApiError extends Error {
  status: number;
  code: string;
  requestId?: string;
  constructor(data: Dict, status: number) {
    super(
      typeof data.detail === "string"
        ? data.detail
        : Array.isArray(data.detail)
          ? data.detail
              .map((d: Dict) => `${(d.loc || []).slice(1).join(".")}: ${d.msg}`)
              .join("; ")
          : data.title || "Не удалось выполнить запрос",
    );
    this.status = status;
    this.code = data.code || "REQUEST_FAILED";
    this.requestId = data.request_id;
  }
}
export async function api<T = Dict>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  const method = (options.method || "GET").toUpperCase();
  const mutation = !["GET", "HEAD", "OPTIONS"].includes(method);
  const anonymousWrite = ["/auth/login", "/auth/register"].includes(path);
  // Standalone pages (e.g. an exam restored after reload) don't mount the
  // workspace session provider. Recover the opaque session's CSRF token before
  // their first write, using one request for concurrent writes. Never weaken
  // server validation or persist the token in browser storage.
  if (mutation && !anonymousWrite && !csrf) {
    csrfRefresh ??= api<Me>("/auth/me")
      .then(() => {
        if (!csrf)
          throw new ApiError(
            {
              code: "SESSION_CSRF_UNAVAILABLE",
              detail: "Обновите страницу и войдите снова.",
            },
            403,
          );
      })
      .finally(() => {
        csrfRefresh = null;
      });
    await csrfRefresh;
  }
  if (options.body && !(options.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  if (mutation && csrf) headers.set("X-CSRF-Token", csrf);
  const response = await fetch(`/api/v1${path}`, {
    ...options,
    headers,
    credentials: "same-origin",
    cache: "no-store",
  });
  const contentType = response.headers.get("content-type") || "";
  const data = contentType.includes("json")
    ? await response.json().catch(() => ({}))
    : {};
  if (!response.ok) {
    if (
      typeof window !== "undefined" &&
      response.status === 401 &&
      !path.startsWith("/auth/login")
    )
      window.dispatchEvent(new Event("vector:session-expired"));
    if (
      typeof window !== "undefined" &&
      data.code === "PROCESSING_CONSENT_REQUIRED"
    )
      window.dispatchEvent(new Event("vector:consent-required"));
    throw new ApiError(data, response.status);
  }
  if (data.csrf_token) setCSRF(data.csrf_token);
  return data as T;
}
export const post = <T = Dict>(path: string, body: unknown = {}) =>
  api<T>(path, { method: "POST", body: JSON.stringify(body) });
export const patch = <T = Dict>(path: string, body: unknown) =>
  api<T>(path, { method: "PATCH", body: JSON.stringify(body) });
export const put = <T = Dict>(path: string, body: unknown) =>
  api<T>(path, { method: "PUT", body: JSON.stringify(body) });
export function items<T = Dict>(data: unknown): T[] {
  if (Array.isArray(data)) return data;
  const d = data as Dict | undefined;
  return Array.isArray(d?.items) ? d.items : [];
}
export const money = (value: unknown) =>
  new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 }).format(
    Number(value || 0),
  );
export const date = (value: unknown) =>
  value
    ? new Date(String(value)).toLocaleDateString("ru-RU", {
        day: "numeric",
        month: "short",
        year: "numeric",
      })
    : "—";
export const specLabels: Record<string, string> = {
  backend: "Backend-разработка",
  frontend: "Frontend-разработка",
  qa: "Тестирование",
  devops: "DevOps / SRE",
  data: "Аналитика данных",
  data_analytics: "Аналитика данных",
  security: "Информационная безопасность",
};
export const specName = (v: unknown) =>
  specLabels[String(v)] || String(v || "Специализация не выбрана");
export const gradeName = (v: unknown) =>
  String(v).toLowerCase() === "intern"
    ? "Стажёр"
    : String(v || "Не подтверждён").replace(/^./, (x) => x.toUpperCase());
export const statusLabels: Record<string, string> = {
  sent: "Отправлено",
  viewed: "Просмотрено",
  accepted: "Принято",
  declined: "Отклонено",
  withdrawn: "Отозвано",
  expired: "Истекло",
  pending: "Ожидает ответа",
  completed: "Завершён",
  active: "В процессе",
  submitted: "Проверяется",
  published: "Опубликована",
  draft: "Черновик",
  new: "Новый отклик",
  shortlisted: "В подборке",
  interview: "Собеседование",
  hired: "Нанят",
  review: "На рассмотрении",
  offer: "Предложение",
  in_progress: "В процессе",
  withdrawn_by_candidate: "Закрыто кандидатом",
  rejected: "Отклонён",
};
export const statusName = (s: unknown) =>
  statusLabels[String(s).toLowerCase()] || String(s || "—");

export const evidenceName = (source: unknown) =>
  (
    ({
      SELF_DECLARED: "Заявлено кандидатом",
      ASSESSMENT_VERIFIED: "Проверено экзаменом",
      PRACTICE_OBSERVED: "Наблюдение в практике",
      NEED_PRACTICE_OBSERVED: "Практика по потребности компании",
      COMPANY_REVIEWED: "Ручная проверка компанией",
      FSP_DEMO_CONFIRMED: "Демонстрационный реестр ФСП",
      FSP_REGISTRY_VERIFIED: "Официальный реестр ФСП",
    }) as Record<string, string>
  )[String(source)] || String(source || "Источник не указан");
export const evidenceSynthetic = (e: Dict) =>
  e.origin === "SYNTHETIC_SEED" ||
  e.source === "SYNTHETIC_SEED" ||
  e.scope?.mode === "synthetic_fixture" ||
  e.calibration_status === "synthetic_fixture";
export const evidenceLabel = (e: Dict) => {
  if (evidenceSynthetic(e)) return "Синтетический пример";
  if (e.source !== "ASSESSMENT_VERIFIED") return evidenceName(e.source);
  if (e.is_demo) return "Демонстрационная проверка";
  const status = String(e.status ?? "active")
    .trim()
    .toLowerCase();
  if (e.revoked || status === "revoked")
    return "Экзамен · свидетельство отозвано";
  if (status === "stale") return "Экзамен · свидетельство устарело";
  if (!["verified", "active"].includes(status))
    return "Экзамен · статус не подтверждён";
  return evidenceName(e.source);
};
export const evidenceVerified = (e: Dict) => {
  const status = String(e.status ?? "active")
    .trim()
    .toLowerCase();
  return (
    e.source === "ASSESSMENT_VERIFIED" &&
    ["verified", "active"].includes(status) &&
    !e.revoked &&
    !e.is_demo &&
    !evidenceSynthetic(e)
  );
};
export function evidenceScore(e: Dict): number | null {
  if (typeof e.score === "number") return e.score;
  if (typeof e.strength === "number") return e.strength * 100;
  return null;
}
export function scopeText(scope: unknown): string {
  if (typeof scope === "string") return scope;
  if (!scope || typeof scope !== "object") return "";
  const s = scope as Dict;
  return [
    s.specialization ? specName(s.specialization) : "",
    s.grade ? gradeName(s.grade) : "",
    Array.isArray(s.stack) ? s.stack.join(" / ") : "",
  ]
    .filter(Boolean)
    .join(" · ");
}
export const explanationText = (value: unknown): string =>
  (typeof value === "string"
    ? value
    : value && typeof value === "object"
      ? String(
          (value as Dict).text ||
            (value as Dict).skill ||
            (value as Dict).label ||
            "Нужно уточнить",
        )
      : String(value || "")
  ).replace(
    /^Категория ([a-z_]+) × ([a-z_]+) /,
    (_, specialization: string, grade: string) =>
      `Категория ${specName(specialization)} × ${gradeName(grade)} `,
  );

export function safeURL(value: unknown): string | undefined {
  try {
    const url = new URL(String(value));
    return ["http:", "https:"].includes(url.protocol) ? url.href : undefined;
  } catch {
    return undefined;
  }
}

type AssessmentRecord = {
  scope?: string;
  demo?: boolean;
  certifies_global_category?: boolean;
  result?: {
    scope?: string;
    passed?: boolean;
    confirmed_grade?: string | null;
  } | null;
};

export function assessmentKind(record: AssessmentRecord) {
  if (
    record.scope === "employer_need_practice" ||
    record.result?.scope === "employer_need_practice"
  )
    return "need_practice";
  if (record.demo) return "demo";
  return "global_category";
}

export function certifiesGrade(record: AssessmentRecord) {
  return (
    assessmentKind(record) === "global_category" &&
    record.certifies_global_category !== false &&
    !!record.result?.passed &&
    typeof record.result.confirmed_grade === "string" &&
    !!record.result.confirmed_grade
  );
}

export function assessmentStatus(
  record: AssessmentRecord & { status?: string; passed?: boolean },
) {
  if (["active", "in_progress"].includes(record.status || ""))
    return "В процессе";
  if (record.status === "expired") return "Время истекло";
  if (record.status !== "completed") return record.status || "—";
  const passed = record.result?.passed ?? record.passed;
  const kind = assessmentKind(record);
  if (kind === "need_practice")
    return passed ? "Практика выполнена" : "Практика не пройдена";
  if (kind === "demo") return "Демонстрация завершена";
  return certifiesGrade(record)
    ? "Подтверждён"
    : passed
      ? "Проверка пройдена"
      : "Не подтверждён";
}

export function needStartBody(context: {
  invitationId?: string;
  vacancyId?: string;
}) {
  const invitationId = context.invitationId?.trim();
  const vacancyId = context.vacancyId?.trim();
  if (!!invitationId === !!vacancyId)
    throw new Error("Для практики нужно одно приглашение или одна вакансия.");
  return invitationId
    ? { invitation_id: invitationId }
    : { vacancy_id: vacancyId! };
}

export function weeklyState(
  data: { completed?: boolean; retry_at?: string | null; opens_at?: string },
  now = Date.now(),
) {
  const retry = data.retry_at ? Date.parse(data.retry_at) : NaN;
  const opens = data.opens_at ? Date.parse(data.opens_at) : NaN;
  return {
    completed: !!data.completed,
    retryBlocked: Number.isFinite(retry) && retry > now,
    notOpen: Number.isFinite(opens) && opens > now,
  };
}

export function availabilityState(
  data: {
    specialization?: string;
    items?: {
      grade: string;
      allowed: boolean;
      next_allowed_at?: string;
      reason?: string;
    }[];
    active_attempt?: {
      id: string;
      specialization: string;
      grade: string;
      scope?: string;
    } | null;
  } | null,
  specialization: string,
  grade: string,
) {
  const ready = data?.specialization === specialization;
  const policy = ready
    ? data?.items?.find((entry) => entry.grade === grade)
    : undefined;
  const active = ready ? data?.active_attempt : undefined;
  const resumeId =
    active &&
    (active.scope || "global_category") === "global_category" &&
    active.specialization === specialization &&
    active.grade === grade
      ? active.id
      : undefined;
  return {
    ready: ready && !!policy,
    policy,
    active,
    resumeId,
    conflict: !!active && !resumeId,
    allowed: !!resumeId || (ready && !!policy?.allowed && !active),
  };
}

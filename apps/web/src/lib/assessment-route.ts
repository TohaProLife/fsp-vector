export type AssessmentRoute = {
  id: string;
  available?: boolean;
  grades?: string[];
  stacks?: string[];
  allowed_contexts?: string[];
  default_contexts?: string[];
  context_aliases?: Record<string, string>;
};
const normalized = (s: string) =>
  s.trim().replace(/\s+/g, " ").toLocaleLowerCase("en");
const unique = (values: string[]) =>
  Array.from(
    new Map(
      values.filter(Boolean).map((v) => [normalized(v), v.trim()]),
    ).values(),
  );
export function routeDefaults(route?: AssessmentRoute): string[] {
  if (!route) return [];
  if (route.default_contexts?.length) return unique(route.default_contexts);
  return unique((route.stacks?.[0] || "").split("/").map((s) => s.trim()));
}
export function routeContexts(route?: AssessmentRoute): string[] {
  if (!route) return [];
  if (route.allowed_contexts?.length) return unique(route.allowed_contexts);
  return unique(
    (route.stacks || []).flatMap((s) => s.split("/").map((v) => v.trim())),
  );
}
export function validateRoute(
  route: AssessmentRoute | undefined,
  grade: string,
  values: string[],
) {
  const empty = {
    valid: false,
    canonical: [] as string[],
    unknown: [] as string[],
    aliases: [] as string[],
    message: "",
  };
  if (!route || route.available === false)
    return { ...empty, message: "Выбери доступную специализацию." };
  if (route.grades?.length && !route.grades.includes(grade))
    return {
      ...empty,
      message: "Выбери доступный для этого маршрута уровень.",
    };
  if (!values.length)
    return {
      ...empty,
      message: "Укажи хотя бы один поддерживаемый контекст проверки.",
    };
  const allowed = routeContexts(route);
  const allowedMap = new Map(
    allowed.map((value) => [normalized(value), value]),
  );
  const descriptors = new Map(
    (route.stacks || []).map((value) => [normalized(value), value]),
  );
  const aliasMap = new Map(
    Object.entries(route.context_aliases || {}).map(([alias, target]) => [
      normalized(alias),
      target,
    ]),
  );
  const canonical: string[] = [];
  const unknown: string[] = [];
  const aliases: string[] = [];
  for (const raw of values) {
    const descriptor = descriptors.get(normalized(raw));
    const atoms = descriptor
      ? descriptor.split("/").map((v) => v.trim())
      : [raw.trim()];
    for (const atom of atoms) {
      const target = aliasMap.get(normalized(atom)) || atom;
      const accepted = allowedMap.get(normalized(target));
      if (!accepted) {
        unknown.push(atom);
        continue;
      }
      canonical.push(accepted);
      if (normalized(atom) !== normalized(accepted))
        aliases.push(`${atom} → ${accepted}`);
    }
  }
  return {
    valid: unknown.length === 0,
    canonical: unique(canonical),
    unknown: unique(unknown),
    aliases: unique(aliases),
    message: unknown.length
      ? `Банк не проверяет этот контекст: ${unique(unknown).join(", ")}. Выбери темы из доступного списка.`
      : "",
  };
}

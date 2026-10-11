/** Labels only: evidence IDs and scoring remain server-owned. */
const labels: Record<string, string> = {
  api: "Проектирование API",
  sql: "Работа с SQL",
  reliability: "Надёжность сервисов",
  testing: "Модульное тестирование",
  javascript: "JavaScript",
  state: "Состояние интерфейса",
  accessibility: "Доступность",
  web_security: "Безопасность веб-приложений",
  test_design: "Проектирование тестов",
  observability: "Наблюдаемость",
  containers: "Контейнеризация",
  networking: "Сети и HTTP",
  statistics: "Статистика",
  data_quality: "Качество данных",
  interpretation: "Интерпретация данных",
  authorization: "Авторизация",
  cryptography: "Криптографические примитивы",
  incident_response: "Разбор инцидентов",
};
export function competencyLabel(value: unknown): string {
  const key = typeof value === "string" ? value : "";
  return labels[key] || key || "Компетенция";
}

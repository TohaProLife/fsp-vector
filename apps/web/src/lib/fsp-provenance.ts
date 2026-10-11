import { type Dict, evidenceSynthetic } from "./api";

export function fspProvenance(record?: Dict) {
  const source = String(record?.source || "");
  const demo =
    record?.is_demo === true ||
    evidenceSynthetic(record || {}) ||
    ["FSP_DEMO_CONFIRMED", "FSP_DEMO_REGISTRY"].includes(source);
  const status = String(record?.status || "active")
    .trim()
    .toLowerCase();
  const revoked =
    record?.revoked === true || ["revoked", "record_revoked"].includes(status);
  const active = [
    "active",
    "verified",
    "sync_ok",
    "linked",
    "verified_demo",
    "linked_no_history",
  ].includes(status);
  const label = demo
    ? "Демонстрационный реестр ФСП"
    : source === "FSP_REGISTRY_VERIFIED"
      ? "Официальный реестр ФСП"
      : "Источник ФСП не подтверждён";
  if (revoked) return { label: `${label} · отозвано`, tone: "red" as const };
  if (!active)
    return { label: `${label} · требуется проверка`, tone: "neutral" as const };
  return {
    label,
    tone: demo
      ? ("amber" as const)
      : source === "FSP_REGISTRY_VERIFIED"
        ? ("green" as const)
        : ("neutral" as const),
  };
}

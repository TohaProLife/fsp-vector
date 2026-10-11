import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import ts from "typescript";

const source = await readFile(
  new URL("../src/lib/api.ts", import.meta.url),
  "utf8",
);
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022,
  },
}).outputText;
const exports = {};
new Function("exports", compiled)(exports);
const { evidenceLabel, evidenceVerified } = exports;

test("exam-shaped synthetic evidence never earns a verified badge or real exam label", () => {
  for (const marker of [
    { origin: "SYNTHETIC_SEED" },
    { scope: { mode: "synthetic_fixture" } },
    { calibration_status: "synthetic_fixture" },
  ]) {
    const e = {
      source: "ASSESSMENT_VERIFIED",
      status: "verified",
      attempt_id: "seed-reference",
      ...marker,
    };
    assert.equal(evidenceVerified(e), false);
    assert.equal(evidenceLabel(e), "Синтетический пример");
  }
});
test("demo assessment, real assessment and revoked evidence remain distinct", () => {
  const actual = {
    source: "ASSESSMENT_VERIFIED",
    status: "verified",
    attempt_id: "saved-attempt",
  };
  assert.equal(evidenceVerified(actual), true);
  assert.equal(evidenceLabel(actual), "Проверено экзаменом");
  assert.equal(evidenceVerified({ ...actual, is_demo: true }), false);
  assert.equal(
    evidenceLabel({ ...actual, is_demo: true }),
    "Демонстрационная проверка",
  );
  assert.equal(evidenceVerified({ ...actual, status: "revoked" }), false);
});
test("declarations and registry evidence retain their source without exam verification", () => {
  for (const [source, label] of [
    ["SELF_DECLARED", "Заявлено кандидатом"],
    ["FSP_DEMO_CONFIRMED", "Демонстрационный реестр ФСП"],
    ["FSP_REGISTRY_VERIFIED", "Официальный реестр ФСП"],
  ]) {
    assert.equal(evidenceLabel({ source }), label);
    assert.equal(evidenceVerified({ source, status: "verified" }), false);
  }
});
test("negative or unknown status cannot become a verified proof", () => {
  for (const status of [
    "revoked",
    "stale",
    "failed",
    "unverified",
    "self_declared",
    "REVOKED",
    " Stale ",
    "unknown",
    "",
  ]) {
    assert.equal(
      evidenceVerified({ source: "ASSESSMENT_VERIFIED", status }),
      false,
      status,
    );
  }
  assert.equal(
    evidenceVerified({
      source: "ASSESSMENT_VERIFIED",
      status: "verified",
      revoked: true,
    }),
    false,
  );
  assert.equal(
    evidenceVerified({ source: "ASSESSMENT_VERIFIED", status: "ACTIVE" }),
    true,
  );
  assert.equal(evidenceVerified({ source: "ASSESSMENT_VERIFIED" }), true);
  assert.equal(
    evidenceLabel({ source: "ASSESSMENT_VERIFIED", status: "STALE" }),
    "Экзамен · свидетельство устарело",
  );
  assert.equal(
    evidenceLabel({
      source: "ASSESSMENT_VERIFIED",
      status: "verified",
      revoked: true,
    }),
    "Экзамен · свидетельство отозвано",
  );
  assert.equal(
    evidenceLabel({ source: "ASSESSMENT_VERIFIED", status: "failed" }),
    "Экзамен · статус не подтверждён",
  );
});

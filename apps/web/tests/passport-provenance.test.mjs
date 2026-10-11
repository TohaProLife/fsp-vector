import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import ts from "typescript";

const source = await readFile(
  new URL("../src/features/candidate.tsx", import.meta.url),
  "utf8",
);
const file = ts.createSourceFile(
  "candidate.tsx",
  source,
  ts.ScriptTarget.Latest,
  true,
  ts.ScriptKind.TSX,
);
const names = [
  "syntheticEvidence",
  "passportEvidenceLabel",
  "passportCategoryProvenance",
];
const declarations = names.map((name) => {
  const declaration = file.statements.find(
    (node) => ts.isFunctionDeclaration(node) && node.name?.text === name,
  );
  assert.ok(declaration, `Missing provenance function ${name}`);
  return declaration.getText(file).replace(/^export\s+/, "");
});
const compiled = ts.transpileModule(declarations.join("\n"), {
  compilerOptions: { target: ts.ScriptTarget.ES2022 },
}).outputText;
const apiSource = await readFile(
  new URL("../src/lib/api.ts", import.meta.url),
  "utf8",
);
const apiCompiled = ts.transpileModule(apiSource, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022,
  },
}).outputText;
const apiExports = {};
new Function("exports", apiCompiled)(apiExports);
const { passportEvidenceLabel, passportCategoryProvenance } = new Function(
  "evidenceSynthetic",
  "evidenceLabel",
  "evidenceVerified",
  `${compiled}; return { passportEvidenceLabel, passportCategoryProvenance };`,
)(
  apiExports.evidenceSynthetic,
  apiExports.evidenceLabel,
  apiExports.evidenceVerified,
);
const profile = (overrides = {}) => ({
  specialization: "backend",
  confirmed_grade: "middle",
  ...overrides,
});
const formalEvidence = (overrides = {}) => ({
  source: "ASSESSMENT_VERIFIED",
  status: "verified",
  attempt_id: "persisted-formal-attempt",
  scope: { specialization: "backend", grade: "middle" },
  ...overrides,
});

test("seeded category and synthetic exam-shaped evidence never claim a real exam", () => {
  const seeded = formalEvidence({
    origin: "SYNTHETIC_SEED",
    is_demo: true,
    scope: {
      specialization: "backend",
      grade: "middle",
      mode: "synthetic_fixture",
    },
  });
  assert.equal(passportEvidenceLabel(seeded), "Синтетический пример");
  assert.deepEqual(
    passportCategoryProvenance(
      profile({
        confirmed_categories: {
          backend: { grade: "middle", source: "SYNTHETIC_SEED" },
        },
      }),
      [seeded],
    ),
    { label: "Синтетический пример", tone: "amber" },
  );
});
test("formal category attempt remains real without source and despite profile fixture marker", () => {
  assert.deepEqual(
    passportCategoryProvenance(
      profile({
        source: "synthetic_fixture",
        confirmed_categories: {
          backend: { grade: "middle", attempt_id: "saved-attempt" },
        },
      }),
      [],
    ),
    { label: "Подтверждена экзаменом", tone: "green" },
  );
  assert.equal(
    passportCategoryProvenance(profile({ source: "synthetic_fixture" }), [
      formalEvidence(),
    ]).label,
    "Подтверждена экзаменом",
  );
});
test("a confirmed grade alone or an unrelated category is not proof of a real exam", () => {
  for (const candidate of [
    profile(),
    profile({
      confirmed_categories: {
        frontend: { grade: "middle", attempt_id: "another-route" },
      },
    }),
    profile({
      confirmed_categories: {
        backend: { grade: "junior", attempt_id: "another-grade" },
      },
    }),
  ]) {
    assert.deepEqual(passportCategoryProvenance(candidate, []), {
      label: "Источник категории не указан",
      tone: "neutral",
    });
  }
  assert.deepEqual(
    passportCategoryProvenance(profile({ confirmed_grade: undefined }), []),
    { label: "До подтверждения", tone: "neutral" },
  );
});
test("evidence must carry a persisted attempt and match the global category scope", () => {
  assert.equal(
    passportCategoryProvenance(profile(), [formalEvidence()]).tone,
    "green",
  );
  for (const invalid of [
    { attempt_id: undefined },
    { is_demo: true },
    { status: "revoked" },
    { origin: "SYNTHETIC_SEED" },
    { source: "SELF_DECLARED" },
    { source: "FSP_REGISTRY_VERIFIED" },
    { source: "NEED_PRACTICE_OBSERVED" },
    { scope: { specialization: "frontend", grade: "middle" } },
    { scope: { specialization: "backend", grade: "senior" } },
    {
      scope: {
        specialization: "backend",
        grade: "middle",
        global_grade: false,
      },
    },
    {
      scope: {
        specialization: "backend",
        grade: "middle",
        company_id: "bounded-company",
      },
    },
  ]) {
    assert.equal(
      passportCategoryProvenance(profile(), [formalEvidence(invalid)]).tone,
      "neutral",
      JSON.stringify(invalid),
    );
  }
});
test("source labels keep declaration, demo registry and real registry distinct", () => {
  assert.equal(
    passportEvidenceLabel({ source: "SELF_DECLARED" }),
    "Заявлено кандидатом",
  );
  assert.equal(
    passportEvidenceLabel({ source: "FSP_DEMO_CONFIRMED", is_demo: true }),
    "Демонстрационный реестр ФСП",
  );
  assert.equal(
    passportEvidenceLabel({ source: "FSP_REGISTRY_VERIFIED" }),
    "Официальный реестр ФСП",
  );
  assert.equal(
    passportEvidenceLabel(formalEvidence({ is_demo: true })),
    "Демонстрационная проверка",
  );
  assert.equal(passportEvidenceLabel(formalEvidence()), "Проверено экзаменом");
});
test("a scoped calibration-only fixture is never a real exam", () => {
  const synthetic = formalEvidence({ calibration_status: "synthetic_fixture" });
  assert.equal(passportEvidenceLabel(synthetic), "Синтетический пример");
  assert.equal(apiExports.evidenceVerified(synthetic), false);
  assert.deepEqual(passportCategoryProvenance(profile(), [synthetic]), {
    label: "Источник категории не указан",
    tone: "neutral",
  });
  assert.deepEqual(
    passportCategoryProvenance(
      profile({
        confirmed_categories: {
          backend: {
            grade: "middle",
            attempt_id: "fixture-reference",
            calibration_status: "synthetic_fixture",
          },
        },
      }),
      [],
    ),
    { label: "Синтетический пример", tone: "amber" },
  );
});
test("negative, unknown and boolean revoked evidence cannot confirm the category", () => {
  for (const status of [
    "revoked",
    "failed",
    "pending",
    "expired",
    "rejected",
    "unverified",
    "not-a-status",
    "",
  ]) {
    const evidence = formalEvidence({ status });
    assert.equal(apiExports.evidenceVerified(evidence), false, status);
    assert.equal(
      passportCategoryProvenance(profile(), [evidence]).tone,
      "neutral",
      status,
    );
  }
  const revoked = formalEvidence({ revoked: true });
  assert.equal(apiExports.evidenceVerified(revoked), false);
  assert.equal(
    passportCategoryProvenance(profile(), [revoked]).tone,
    "neutral",
  );
});
test("active and server-default-active evidence with valid scope can confirm", () => {
  for (const status of ["verified", "active", undefined]) {
    const evidence = formalEvidence({ status });
    assert.equal(apiExports.evidenceVerified(evidence), true);
    assert.equal(
      passportCategoryProvenance(profile(), [evidence]).tone,
      "green",
    );
  }
});

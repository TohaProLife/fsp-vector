import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import ts from "typescript";

const compile = (source) =>
  ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;
const apiExports = {};
new Function(
  "exports",
  compile(
    await readFile(new URL("../src/lib/api.ts", import.meta.url), "utf8"),
  ),
)(apiExports);
const exports = {};
new Function(
  "require",
  "exports",
  compile(
    await readFile(
      new URL("../src/lib/fsp-provenance.ts", import.meta.url),
      "utf8",
    ),
  ),
)(() => apiExports, exports);
const { fspProvenance } = exports;

test("FSP: real and demo registry keep different visible provenance, even if they use the same linked status", () => {
  assert.deepEqual(
    fspProvenance({
      source: "FSP_DEMO_CONFIRMED",
      status: "sync_ok",
      is_demo: true,
    }),
    { label: "Демонстрационный реестр ФСП", tone: "amber" },
  );
  assert.deepEqual(
    fspProvenance({
      source: "FSP_REGISTRY_VERIFIED",
      status: "sync_ok",
      is_demo: false,
    }),
    { label: "Официальный реестр ФСП", tone: "green" },
  );
  assert.equal(
    fspProvenance({ source: "FSP_REGISTRY_VERIFIED", is_demo: true }).tone,
    "amber",
  );
  assert.equal(
    fspProvenance({ source: "FSP_REGISTRY_VERIFIED", origin: "SYNTHETIC_SEED" })
      .tone,
    "amber",
  );
});

test("FSP: revoked, stale and unknown registry records cannot render an active official confirmation", () => {
  for (const record of [{ status: "revoked" }, { revoked: true }]) {
    const result = fspProvenance({
      source: "FSP_REGISTRY_VERIFIED",
      ...record,
    });
    assert.equal(result.tone, "red");
    assert.match(result.label, /отозвано/);
  }
  for (const status of ["sync_stale", "sync_failed", "pending", "unknown"]) {
    const result = fspProvenance({ source: "FSP_REGISTRY_VERIFIED", status });
    assert.equal(result.tone, "neutral");
    assert.match(result.label, /требуется проверка/);
  }
  assert.equal(
    fspProvenance({ status: "sync_ok" }).label,
    "Источник ФСП не подтверждён",
  );
});

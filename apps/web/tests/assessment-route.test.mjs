import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import ts from "typescript";
const source = await readFile(
  new URL("../src/lib/assessment-route.ts", import.meta.url),
  "utf8",
);
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    target: ts.ScriptTarget.ES2022,
    module: ts.ModuleKind.ES2022,
  },
}).outputText;
const { routeDefaults, routeContexts, validateRoute } = await import(
  `data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`
);
const backend = {
  id: "backend",
  available: true,
  grades: ["intern", "junior", "middle", "senior"],
  stacks: ["Python / SQL / API", "TypeScript / SQL / API"],
  allowed_contexts: ["Python", "TypeScript", "SQL", "API"],
  default_contexts: ["Python", "SQL", "API"],
  context_aliases: { "REST API": "API", "rest-api": "API" },
};
test("first route uses canonical initial contexts, not a hardcoded unsupported API spelling", () => {
  assert.deepEqual(routeDefaults(backend), ["Python", "SQL", "API"]);
  assert.equal(
    validateRoute(backend, "intern", routeDefaults(backend)).valid,
    true,
  );
});
test("requested input survives alias validation; canonical contexts are reported separately", () => {
  const supplied = ["  python  ", "REST API", "SQL"];
  const snapshot = [...supplied];
  const r = validateRoute(backend, "intern", supplied);
  assert.equal(r.valid, true);
  assert.deepEqual(r.canonical, ["Python", "API", "SQL"]);
  assert.deepEqual(supplied, snapshot);
  assert.deepEqual(r.aliases, ["REST API → API"]);
});
test("unsupported context and invalid grade are rejected before survey persistence", () => {
  assert.equal(validateRoute(backend, "middle", ["Kubernetes"]).valid, false);
  assert.deepEqual(validateRoute(backend, "middle", ["Kubernetes"]).unknown, [
    "Kubernetes",
  ]);
  assert.equal(validateRoute(backend, "lead", ["Python"]).valid, false);
  assert.equal(validateRoute(backend, "intern", []).valid, false);
});
test("whole route descriptors are expanded into accepted contexts", () => {
  assert.deepEqual(
    validateRoute(backend, "senior", ["TypeScript / SQL / API"]).canonical,
    ["TypeScript", "SQL", "API"],
  );
});
test("catalog without new metadata uses one first descriptor, not mixed route languages", () => {
  const legacy = {
    id: "backend",
    stacks: ["Python / SQL / API", "TypeScript / SQL / API"],
  };
  assert.deepEqual(routeDefaults(legacy), ["Python", "SQL", "API"]);
  assert.equal(
    validateRoute(legacy, "intern", routeDefaults(legacy)).valid,
    true,
  );
});
test("all six live catalog default routes are valid for every advertised grade", async () => {
  const origin = process.env.API_ORIGIN || "http://127.0.0.1:8000";
  const response = await fetch(`${origin}/api/v1/assessments/catalog`);
  assert.equal(response.status, 200);
  const catalog = await response.json();
  assert.equal(catalog.specializations.length, 6);
  for (const route of catalog.specializations) {
    assert.ok(routeDefaults(route).length, route.id);
    for (const grade of route.grades) {
      const checked = validateRoute(route, grade, routeDefaults(route));
      assert.equal(
        checked.valid,
        true,
        `${route.id}/${grade}: ${checked.message}`,
      );
    }
    for (const descriptor of route.stacks) {
      assert.equal(
        validateRoute(route, route.grades[0], [descriptor]).valid,
        true,
        descriptor,
      );
    }
  }
});

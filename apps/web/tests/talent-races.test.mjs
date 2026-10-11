import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import ts from "typescript";

const source = await readFile(
  new URL("../src/features/employer.tsx", import.meta.url),
  "utf8",
);
const file = ts.createSourceFile(
  "employer.tsx",
  source,
  ts.ScriptTarget.Latest,
  true,
  ts.ScriptKind.TSX,
);
const component = file.statements.find(
  (node) => ts.isFunctionDeclaration(node) && node.name?.text === "Talent",
);
const handlers = [
  "fetchCandidates",
  "makeMatch",
  "openDetail",
  "closeDetail",
  "openRun",
  "openCategories",
  "loadRuns",
];
const declarations = handlers.map((name) => {
  const statement = component.body.statements.find(
    (node) =>
      ts.isVariableStatement(node) &&
      node.declarationList.declarations.some(
        (entry) => entry.name.getText(file) === name,
      ),
  );
  assert.ok(statement, `Missing actual Talent handler ${name}`);
  return statement.getText(file);
});
const compiled = ts.transpileModule(declarations.join("\n"), {
  compilerOptions: { target: ts.ScriptTarget.ES2022 },
}).outputText;

function harness({ needId = "selected-need", match = null } = {}) {
  const state = {
    loading: false,
    list: [],
    selected: [],
    detail: null,
    error: undefined,
    detailError: undefined,
    match,
    notifications: [],
  };
  const requests = [];
  const generations = Object.fromEntries(
    [
      "listGeneration",
      "detailGeneration",
      "categoriesGeneration",
      "runsGeneration",
    ].map((name) => [name, { current: 0 }]),
  );
  const request = (method, path, body) =>
    new Promise((resolve, reject) =>
      requests.push({ method, path, body, resolve, reject }),
    );
  const env = {
    ...generations,
    api: (path) => request("GET", path),
    post: (path, body) => request("POST", path, body),
    items: (value) => value?.items ?? [],
    filters: { q: "selected-filter" },
    needId,
    match,
    ctx: { notify: (text) => state.notifications.push(text) },
  };
  for (const name of [
    "Loading",
    "Error",
    "List",
    "Total",
    "Page",
    "Selected",
    "Match",
    "Runs",
    "RunsError",
    "RunsLoading",
    "Detail",
    "DetailError",
    "Categories",
    "CategoriesError",
    "CategoriesLoading",
    "NeedId",
    "Query",
    "Specialization",
    "Grade",
    "Skill",
    "FspOnly",
    "Format",
  ]) {
    const key = name[0].toLowerCase() + name.slice(1);
    env[`set${name}`] = (value) => {
      state[key] = typeof value === "function" ? value(state[key]) : value;
    };
  }
  const calls = new Function(
    ...Object.keys(env),
    `${compiled}; return { ${handlers.join(", ")} };`,
  )(...Object.values(env));
  return { state, requests, generations, ...calls };
}

test("Talent: late search response cannot replace newer filters, selection or loading state", async () => {
  const h = harness();
  const old = h.fetchCandidates(1);
  const current = h.fetchCandidates(2);
  h.requests[0].resolve({ items: [{ id: "wrong-page" }], total: 100 });
  await old;
  assert.equal(h.state.loading, true);
  assert.deepEqual(h.state.list, []);
  h.requests[1].resolve({ items: [{ id: "current-page" }], total: 52 });
  await current;
  assert.deepEqual(h.state.list, [{ id: "current-page" }]);
  assert.equal(h.state.page, 2);
  assert.equal(h.state.total, 52);
  assert.equal(h.state.loading, false);
});

test("Talent: old failed saved read cannot conceal newer successful search", async () => {
  const h = harness();
  const old = h.openRun("old-run");
  const current = h.fetchCandidates();
  h.requests[1].resolve({ items: [{ id: "current" }], total: 1 });
  await current;
  h.requests[0].reject(new Error("old run no longer accessible"));
  await old;
  assert.equal(h.state.error, undefined);
  assert.equal(h.state.loading, false);
  assert.equal(h.state.list[0].id, "current");
});

test("Talent: changing need never refines the former need's immutable saved context", async () => {
  const h = harness({
    needId: "new-need",
    match: { id: "old-run", need_id: "old-need" },
  });
  const pending = h.makeMatch(true);
  assert.equal(h.requests[0].path, "/employer/matches");
  assert.equal(h.requests[0].body.need_id, "new-need");
  h.requests[0].resolve({
    id: "new-run",
    need_id: "new-need",
    items: [],
    total: 0,
  });
  await pending;
  assert.equal(h.state.match.id, "new-run");
  assert.deepEqual(h.state.notifications, ["Подборка сохранена"]);
  h.requests[1].resolve({ items: [] });
});

test("Talent: refining the same need retains its snapshot route", async () => {
  const h = harness({
    needId: "same-need",
    match: { id: "parent-run", need_id: "same-need" },
  });
  const pending = h.makeMatch(true);
  assert.equal(h.requests[0].path, "/employer/matches/parent-run/refine");
  h.requests[0].resolve({ id: "child-run", need_id: "same-need", items: [] });
  await pending;
  assert.deepEqual(h.state.notifications, ["Уточнённая подборка сохранена"]);
  h.requests[1].resolve({ items: [] });
});

test("Talent: an outdated persisted match response cannot replace the current result or notify success", async () => {
  const h = harness();
  const old = h.makeMatch();
  const current = h.fetchCandidates();
  h.requests[1].resolve({ items: [{ id: "current" }], total: 1 });
  await current;
  h.requests[0].resolve({
    id: "late-run",
    need_id: "selected-need",
    items: [{ candidate: { id: "late" } }],
  });
  await old;
  assert.equal(h.state.list[0].id, "current");
  assert.equal(h.state.match, null);
  assert.deepEqual(h.state.notifications, []);
});

test("Talent: failed detail remains retryable, while a closed modal cannot reopen from a late DTO", async () => {
  const h = harness();
  const failed = h.openDetail({ id: "profile" });
  h.requests[0].reject(new Error("404: consent withdrawn"));
  await failed;
  assert.equal(h.state.detail._loading, false);
  assert.equal(h.state.detail._loadFailed, true);
  const retry = h.openDetail(h.state.detail);
  h.closeDetail();
  h.requests[1].resolve({
    id: "profile",
    contacts: { email: "formerly-authorized@example.local" },
  });
  await retry;
  assert.equal(h.state.detail, null);
  assert.equal(h.state.detailError, undefined);
});

test("Talent: older detail failure cannot overwrite a newer authorized projection", async () => {
  const h = harness();
  const old = h.openDetail({ id: "old" });
  const current = h.openDetail({ id: "current" });
  h.requests[1].resolve({ id: "current", alias: "Current safe profile" });
  await current;
  h.requests[0].reject(new Error("old failure"));
  await old;
  assert.equal(h.state.detail.id, "current");
  assert.equal(h.state.detailError, undefined);
});

test("Talent: reopening a saved run restores its actual filters and clears stale comparison selection", async () => {
  const h = harness();
  h.state.selected = ["old-selection"];
  const pending = h.openRun("saved");
  h.requests[0].resolve({
    id: "saved",
    need_id: "snapshot-need",
    total: 2,
    items: [{ candidate: { id: "a" } }],
    filters: {
      q: "saved-query",
      specialization: "backend",
      grade: "middle",
      skill: "SQL",
      fsp_only: true,
      work_format: "remote",
    },
  });
  await pending;
  assert.equal(h.state.needId, "snapshot-need");
  assert.equal(h.state.query, "saved-query");
  assert.equal(h.state.skill, "SQL");
  assert.equal(h.state.fspOnly, true);
  assert.equal(h.state.total, 2);
  assert.deepEqual(h.state.selected, []);
});

test("Talent: closing category modal prevents a late request from reopening it", async () => {
  const h = harness();
  const pending = h.openCategories();
  h.generations.categoriesGeneration.current++;
  h.state.categories = null;
  h.requests[0].resolve({
    items: [{ specialization: "backend", grade: "middle", count: 2 }],
  });
  await pending;
  assert.equal(h.state.categories, null);
});

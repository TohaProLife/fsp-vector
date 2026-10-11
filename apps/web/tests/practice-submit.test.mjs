import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import ts from "typescript";

const source = await readFile(
  new URL("../src/features/hiring.tsx", import.meta.url),
  "utf8",
);
const file = ts.createSourceFile(
  "hiring.tsx",
  source,
  ts.ScriptTarget.Latest,
  true,
  ts.ScriptKind.TSX,
);
let handler;
const visit = (node) => {
  if (
    ts.isJsxAttribute(node) &&
    node.name.getText(file) === "onClick" &&
    node.initializer
      ?.getText(file)
      .includes("`/challenges/${detail.id}/submit`")
  )
    handler = node.initializer.expression.getText(file);
  ts.forEachChild(node, visit);
};
visit(file);
assert.ok(handler, "Actual practice submission handler missing");
const compiled = ts.transpileModule(`const submit = ${handler};`, {
  compilerOptions: { target: ts.ScriptTarget.ES2022 },
}).outputText;
function harness() {
  const state = {
    result: null,
    error: undefined,
    busy: false,
    weeklyVersion: 0,
    notifications: [],
    reloads: 0,
  };
  const requests = [];
  const generation = { current: 1 };
  const submit = new Function(
    "detailGeneration",
    "setBusy",
    "setActionError",
    "post",
    "detail",
    "answer",
    "setResult",
    "reload",
    "setWeeklyVersion",
    "ctx",
    `${compiled}; return submit;`,
  )(
    generation,
    (value) => {
      state.busy = value;
    },
    (value) => {
      state.error = value;
    },
    (path, body) =>
      new Promise((resolve, reject) =>
        requests.push({ path, body, resolve, reject }),
      ),
    { id: "selected-practice" },
    "Selected answer",
    (value) => {
      state.result = value;
    },
    async () => {
      state.reloads++;
    },
    (value) => {
      state.weeklyVersion = value(state.weeklyVersion);
    },
    {
      notify: (value) => state.notifications.push(value),
      refresh: () => {
        throw new Error("Remount would hide the persisted result");
      },
    },
  );
  return { state, requests, generation, submit };
}
test("Practice: actual persisted result remains visible while owned resources refresh", async () => {
  const h = harness();
  const pending = h.submit();
  assert.equal(h.requests[0].path, "/challenges/selected-practice/submit");
  assert.deepEqual(h.requests[0].body, { answer: "Selected answer" });
  h.requests[0].resolve({
    result: { score: 82, passed: true, feedback: "Persisted rubric result" },
  });
  await pending;
  assert.deepEqual(h.state.result, {
    score: 82,
    passed: true,
    feedback: "Persisted rubric result",
  });
  assert.equal(h.state.error, undefined);
  assert.equal(h.state.busy, false);
  assert.equal(h.state.reloads, 1);
  assert.equal(h.state.weeklyVersion, 1);
  assert.deepEqual(h.state.notifications, ["Ответ сохранён"]);
});
test("Practice: result from a closed task cannot be attributed to a newly opened task", async () => {
  const h = harness();
  const pending = h.submit();
  h.generation.current++;
  h.requests[0].resolve({ result: { score: 100, passed: true } });
  await pending;
  assert.equal(h.state.result, null);
  assert.equal(h.state.reloads, 0);
  assert.deepEqual(h.state.notifications, []);
});
test("Practice: failed persistence shows error without result or success toast", async () => {
  const h = harness();
  const pending = h.submit();
  const error = new Error("403: company practice no longer accessible");
  h.requests[0].reject(error);
  await pending;
  assert.equal(h.state.error, error);
  assert.equal(h.state.result, null);
  assert.equal(h.state.busy, false);
  assert.deepEqual(h.state.notifications, []);
});

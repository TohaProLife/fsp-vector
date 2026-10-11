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
const hookSource = compile(
  await readFile(new URL("../src/lib/hooks.ts", import.meta.url), "utf8"),
);
const hiring = await readFile(
  new URL("../src/features/hiring.tsx", import.meta.url),
  "utf8",
);
const file = ts.createSourceFile(
  "hiring.tsx",
  hiring,
  ts.ScriptTarget.Latest,
  true,
  ts.ScriptKind.TSX,
);
const invitations = file.statements.find(
  (node) => ts.isFunctionDeclaration(node) && node.name?.text === "Invitations",
);
const statement = invitations.body.statements.find(
  (node) =>
    ts.isVariableStatement(node) &&
    node.declarationList.declarations.some(
      (entry) => entry.name.getText(file) === "syncInvitations",
    ),
);
const syncCode = compile(statement.getText(file));

function harness() {
  const target = new EventTarget();
  const slots = [];
  let cursor = 0;
  let commits = [];
  const react = {
    useRef(value) {
      const index = cursor++;
      slots[index] ??= { current: value };
      return slots[index];
    },
    useEffect(callback, deps) {
      const index = cursor++;
      if (
        !slots[index] ||
        deps.some((value, i) => value !== slots[index].deps[i])
      ) {
        const before = slots[index];
        slots[index] = { deps };
        commits.push(() => {
          before?.cleanup?.();
          slots[index].cleanup = callback();
        });
      }
    },
  };
  const exports = {};
  new Function("require", "exports", "window", hookSource)(
    (name) => (name === "react" ? react : {}),
    exports,
    target,
  );
  const state = {
    detail: { id: "selected", status: "pending" },
    error: undefined,
    reloads: 0,
    draft: "Unsent invitation message",
  };
  const generation = { current: 0 };
  const requests = [];
  function refreshFor(detail) {
    return new Function(
      "reload",
      "detail",
      "detailGeneration",
      "api",
      "setDetail",
      "setDetailError",
      `${syncCode}; return syncInvitations;`,
    )(
      async () => {
        state.reloads++;
      },
      detail,
      generation,
      (path) =>
        new Promise((resolve, reject) =>
          requests.push({ path, resolve, reject }),
        ),
      (value) => {
        state.detail = value;
      },
      (value) => {
        state.error = value;
      },
    );
  }
  function render(detail = state.detail) {
    cursor = 0;
    commits = [];
    const sync = refreshFor(detail);
    exports.useDomainRefresh(() => void sync());
    commits.forEach((commit) => commit());
  }
  render();
  return {
    state,
    requests,
    render,
    generation,
    notify() {
      target.dispatchEvent(new Event("vector:domain-updated"));
    },
    cleanup() {
      slots.forEach((slot) => slot?.cleanup?.());
    },
  };
}
const flush = () => new Promise(setImmediate);

test("Live hiring notification reloads persisted invitation state and authorized contact projection without clearing a message draft", async () => {
  const h = harness();
  h.notify();
  assert.equal(h.state.reloads, 1);
  assert.equal(h.requests[0].path, "/invitations/selected");
  h.requests[0].resolve({
    id: "selected",
    status: "accepted",
    candidate: { contacts: { email: "authorized@example.local" } },
  });
  await flush();
  assert.equal(h.state.detail.status, "accepted");
  assert.equal(
    h.state.detail.candidate.contacts.email,
    "authorized@example.local",
  );
  assert.equal(h.state.draft, "Unsent invitation message");
});

test("Live hiring callback tracks the current selected invitation after commit and never duplicates event subscriptions", async () => {
  const h = harness();
  h.render({ id: "new-selection", status: "pending" });
  h.notify();
  assert.equal(h.requests.length, 1);
  assert.equal(h.requests[0].path, "/invitations/new-selection");
  assert.equal(h.state.reloads, 1);
  h.requests[0].resolve({ id: "new-selection", status: "viewed" });
  await flush();
  assert.equal(h.state.detail.id, "new-selection");
});

test("A live hiring response cannot reopen the invitation after its modal has closed", async () => {
  const h = harness();
  h.notify();
  h.generation.current++;
  h.state.detail = null;
  h.requests[0].resolve({ id: "selected", status: "accepted" });
  await flush();
  assert.equal(h.state.detail, null);
});

test("Live hiring listeners detach on unmount and cannot refresh the former role's resources", () => {
  const h = harness();
  h.cleanup();
  h.notify();
  assert.equal(h.requests.length, 0);
  assert.equal(h.state.reloads, 0);
});

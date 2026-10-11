import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import ts from "typescript";

const source = await readFile(
  new URL("../src/lib/hooks.ts", import.meta.url),
  "utf8",
);
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    target: ts.ScriptTarget.ES2022,
    module: ts.ModuleKind.CommonJS,
  },
}).outputText;
const flush = () => new Promise(setImmediate);

// Execute the production hook with controlled commit/cleanup boundaries. The
// deferred transport makes ordering deterministic without a browser or a DB.
function harness(initialPath) {
  const slots = [];
  const requests = [];
  let cursor = 0;
  let commits = [];
  let path = initialPath;
  let writes = 0;
  const equal = (before, after) =>
    !!before &&
    before.length === after.length &&
    before.every((value, i) => Object.is(value, after[i]));
  const react = {
    useState(initial) {
      const i = cursor++;
      slots[i] ??= { value: initial };
      return [
        slots[i].value,
        (value) => {
          writes++;
          slots[i].value =
            typeof value === "function" ? value(slots[i].value) : value;
        },
      ];
    },
    useRef(initial) {
      const i = cursor++;
      slots[i] ??= { ref: { current: initial } };
      return slots[i].ref;
    },
    useCallback(callback, deps) {
      const i = cursor++;
      if (!slots[i] || !equal(slots[i].deps, deps))
        slots[i] = { callback, deps };
      return slots[i].callback;
    },
    useEffect(callback, deps) {
      const i = cursor++;
      if (!slots[i] || !equal(slots[i].deps, deps)) {
        const before = slots[i];
        slots[i] = { deps };
        commits.push(() => {
          before?.cleanup?.();
          slots[i].cleanup = callback();
        });
      }
    },
  };
  const api = (requestedPath) =>
    new Promise((resolve, reject) => {
      requests.push({ path: requestedPath, resolve, reject });
    });
  const exports = {};
  new Function("require", "exports", compiled)(
    (name) => (name === "react" ? react : { api }),
    exports,
  );
  const read = (nextPath = path) => {
    path = nextPath;
    cursor = 0;
    commits = [];
    const result = exports.useResource(path);
    commits.forEach((commit) => commit());
    return result;
  };
  read();
  return {
    read,
    requests,
    get writes() {
      return writes;
    },
    unmount() {
      slots.forEach((slot) => slot.cleanup?.());
    },
  };
}

test("a late response from the former path cannot replace the selected resource", async () => {
  const h = harness("/A");
  h.read("/B");
  assert.deepEqual(
    h.requests.map((request) => request.path),
    ["/A", "/B"],
  );
  h.requests[1].resolve({ category: "B" });
  await flush();
  h.requests[0].resolve({ category: "A" });
  await flush();
  assert.deepEqual(h.read().data, { category: "B" });
  assert.equal(h.read().loading, false);
  assert.equal(h.read().error, undefined);
});

test("a callback retained from the previous path cannot start a request or replace the selected resource", async () => {
  const h = harness("/A");
  const oldReload = h.read().reload;
  h.read("/B");
  h.requests[1].resolve({ category: "B" });
  await flush();
  const writes = h.writes;
  await oldReload();
  assert.equal(h.requests.length, 2);
  assert.equal(h.writes, writes);
  assert.deepEqual(h.read().data, { category: "B" });
  assert.equal(h.read().loading, false);
});

test("an older reload cannot end loading or show data while the newer request is pending", async () => {
  const h = harness("/same");
  const latest = h.read().reload();
  h.requests[0].resolve({ revision: 1 });
  await flush();
  assert.equal(h.read().loading, true);
  assert.equal(h.read().data, null);
  h.requests[1].resolve({ revision: 2 });
  await latest;
  assert.equal(h.read().loading, false);
  assert.deepEqual(h.read().data, { revision: 2 });
});

test("a stale error cannot conceal a successfully refreshed resource", async () => {
  const h = harness("/same");
  const latest = h.read().reload();
  h.requests[1].resolve({ visible: true });
  await latest;
  h.requests[0].reject(new Error("Old transport failed"));
  await flush();
  assert.equal(h.read().error, undefined);
  assert.deepEqual(h.read().data, { visible: true });
});

test("completion after cleanup performs no state updates and detached reload starts no request", async () => {
  const h = harness("/private");
  const detachedReload = h.read().reload;
  h.unmount();
  const writes = h.writes;
  h.requests[0].resolve({ contact: "synthetic@example.invalid" });
  await flush();
  await detachedReload();
  assert.equal(h.writes, writes);
  assert.equal(h.requests.length, 1);
});

test("a current failure ends loading and a deliberate retry clears the error and recovers", async () => {
  const h = harness("/recoverable");
  const error = new Error("Temporary failure");
  h.requests[0].reject(error);
  await flush();
  assert.equal(h.read().loading, false);
  assert.equal(h.read().error, error);
  const retry = h.read().reload();
  assert.equal(h.read().loading, true);
  assert.equal(h.read().error, undefined);
  h.requests[1].resolve({ recovered: true });
  await retry;
  assert.equal(h.read().loading, false);
  assert.deepEqual(h.read().data, { recovered: true });
});

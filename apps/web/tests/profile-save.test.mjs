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
const component = file.statements.find(
  (node) =>
    ts.isFunctionDeclaration(node) && node.name?.text === "ProfileEditor",
);
const statement = component.body.statements.find(
  (node) =>
    ts.isVariableStatement(node) &&
    node.declarationList.declarations.some(
      (entry) => entry.name.getText(file) === "submit",
    ),
);
const compiled = ts.transpileModule(statement.getText(file), {
  compilerOptions: { target: ts.ScriptTarget.ES2022 },
}).outputText;

test("Profile save preserves verified account email and sends only server-authorized contact fields", async () => {
  const state = {
    busy: false,
    error: new Error("prior error"),
    import: { draft: true },
    calls: [],
    notifications: [],
    reloads: 0,
  };
  class FormData {
    constructor(value) {
      this.value = value;
    }
    get(key) {
      return this.value[key] ?? "";
    }
  }
  const submit = new Function(
    "FormData",
    "setBusy",
    "setMutationError",
    "patch",
    "split",
    "ctx",
    "setImportData",
    "reload",
    `${compiled}; return submit;`,
  )(
    FormData,
    (value) => {
      state.busy = value;
    },
    (value) => {
      state.error = value;
    },
    async (path, body) => {
      state.calls.push({ path, body });
    },
    (value) =>
      String(value)
        .split(",")
        .map((part) => part.trim())
        .filter(Boolean),
    { notify: (value) => state.notifications.push(value) },
    (value) => {
      state.import = value;
    },
    async () => {
      state.reloads++;
    },
  );
  await submit({
    preventDefault() {},
    currentTarget: {
      name: "Synthetic candidate",
      title: "Backend",
      bio: "Fixture",
      city: "Москва",
      skills: "Python, SQL",
      contact_email: "verified-account@example.local",
      phone: "+70000000000",
      telegram: "@fixture",
      salary_from: "180000",
      salary_to: "240000",
      work_format: "remote",
      employment: "full_time",
    },
  });
  assert.equal(state.calls.length, 1);
  assert.equal(state.calls[0].path, "/candidate/profile");
  assert.deepEqual(state.calls[0].body.contacts, {
    phone: "+70000000000",
    telegram: "@fixture",
  });
  assert.deepEqual(state.calls[0].body.skills, ["Python", "SQL"]);
  assert.equal(state.calls[0].body.preferences.salary_from, 180000);
  assert.equal(state.calls[0].body.preferences.salary_to, 240000);
  assert.equal(state.error, undefined);
  assert.equal(state.busy, false);
  assert.equal(state.import, null);
  assert.equal(state.reloads, 1);
  assert.deepEqual(state.notifications, ["Профиль сохранён"]);
});

test("Profile save transport failure shows its actual error and never reports success", async () => {
  const error = new Error("409: profile update rejected");
  const state = { error: undefined, notifications: [] };
  class FormData {
    get() {
      return "";
    }
  }
  const submit = new Function(
    "FormData",
    "setBusy",
    "setMutationError",
    "patch",
    "split",
    "ctx",
    "setImportData",
    "reload",
    `${compiled}; return submit;`,
  )(
    FormData,
    () => {},
    (value) => {
      state.error = value;
    },
    async () => {
      throw error;
    },
    () => [],
    { notify: (value) => state.notifications.push(value) },
    () => {
      throw new Error("Unexpected draft reset");
    },
    () => {
      throw new Error("Unexpected reload");
    },
  );
  await submit({ preventDefault() {}, currentTarget: {} });
  assert.equal(state.error, error);
  assert.deepEqual(state.notifications, []);
});

async function saveSalary(values) {
  const state = { calls: [], notifications: [], error: undefined, busy: false };
  class FormData {
    constructor(value) {
      this.value = value;
    }
    get(key) {
      return this.value[key] ?? "";
    }
  }
  const submit = new Function(
    "FormData",
    "setBusy",
    "setMutationError",
    "patch",
    "split",
    "ctx",
    "setImportData",
    "reload",
    `${compiled}; return submit;`,
  )(
    FormData,
    (value) => {
      state.busy = value;
    },
    (value) => {
      state.error = value;
    },
    async (path, body) => {
      state.calls.push({ path, body });
    },
    () => [],
    { notify: (value) => state.notifications.push(value) },
    () => {},
    async () => {},
  );
  await submit({
    preventDefault() {},
    currentTarget: {
      name: "Новый участник",
      work_format: "remote",
      employment: "full_time",
      ...values,
    },
  });
  return state;
}

test("A new profile saves with empty optional salary without manufacturing zero bounds", async () => {
  const state = await saveSalary({ salary_from: "", salary_to: "" });
  assert.equal(state.calls.length, 1);
  assert.deepEqual(state.calls[0].body.preferences, {
    work_format: "remote",
    employment: "full_time",
  });
  assert.equal(state.error, undefined);
  assert.equal(state.busy, false);
  assert.deepEqual(state.notifications, ["Профиль сохранён"]);
});

test("A partial optional salary range requires both bounds and never sends an invalid mutation", async () => {
  for (const values of [
    { salary_from: "80000", salary_to: "" },
    { salary_from: "", salary_to: "120000" },
  ]) {
    const state = await saveSalary(values);
    assert.equal(state.calls.length, 0);
    assert.match(state.error.message, /Укажите обе границы/);
    assert.equal(state.busy, false);
    assert.deepEqual(state.notifications, []);
  }
});

test("Explicit zero and invalid salary ranges stay errors rather than becoming missing preferences", async () => {
  for (const [low, high] of [
    ["0", "0"],
    ["0", "120000"],
    ["80000", "0"],
    ["120000", "80000"],
    ["80000", "10000001"],
    ["-1", "80000"],
    ["80000.5", "120000"],
    ["NaN", "120000"],
  ]) {
    const state = await saveSalary({ salary_from: low, salary_to: high });
    assert.equal(state.calls.length, 0, `${low}–${high} must not reach PATCH`);
    assert.match(state.error.message, /Зарплата:/);
    assert.equal(state.busy, false);
    assert.deepEqual(state.notifications, []);
  }
});

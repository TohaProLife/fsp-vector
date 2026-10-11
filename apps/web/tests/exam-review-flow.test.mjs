import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import ts from "typescript";

const source = await readFile(
  new URL("../src/features/exam.tsx", import.meta.url),
  "utf8",
);
const file = ts.createSourceFile(
  "exam.tsx",
  source,
  ts.ScriptTarget.Latest,
  true,
  ts.ScriptKind.TSX,
);
const exam = file.statements.find(
  (node) => ts.isFunctionDeclaration(node) && node.name?.text === "Exam",
);
const helperSource = await readFile(
  new URL("../src/lib/assessment-review.ts", import.meta.url),
  "utf8",
);
const helpers = await import(
  `data:text/javascript;base64,${Buffer.from(ts.transpileModule(helperSource, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 } }).outputText).toString("base64")}`
);
const callbackSource = (name) => {
  const declaration = exam.body.statements
    .filter(ts.isVariableStatement)
    .flatMap((node) => [...node.declarationList.declarations])
    .find((node) => node.name.getText(file) === name);
  return ts.transpileModule(
    `const callback = ${declaration.initializer.arguments[0].getText(file)};`,
    { compilerOptions: { target: ts.ScriptTarget.ES2022 } },
  ).outputText;
};
const compiled = {
  beginReview: callbackSource("beginReview"),
  submit: callbackSource("submit"),
};
const digest = "a".repeat(64);
const receipt = (overrides = {}) => ({
  answered: 1,
  total: 1,
  structural_ready: true,
  issues: [],
  public_form_sha256: digest,
  saved_answers_sha256: digest,
  prospective_answers_sha256: digest,
  review_token: digest,
  limitations: [],
  ...overrides,
});
const flush = () => new Promise(setImmediate);
class ApiError extends Error {
  constructor(code) {
    super(code);
    this.code = code;
  }
}
function harness() {
  const state = {
    review: null,
    reviewing: false,
    reviewError: undefined,
    confirm: false,
    submitting: false,
    dirty: true,
    allowMissing: false,
    loads: 0,
  };
  const requests = [];
  const env = {
    ...helpers,
    ApiError,
    id: "synthetic-attempt",
    answersRef: { current: { first: [{ value: 7 }] } },
    versionRef: { current: 1 },
    submittedRef: { current: false },
    reviewRef: { current: false },
    reviewGeneration: { current: 0 },
    savePending: { current: null },
    dirtyRef: { current: true },
    load: async () => {
      state.loads++;
    },
    put: (path, body) =>
      new Promise((resolve, reject) =>
        requests.push({ method: "PUT", path, body, resolve, reject }),
      ),
    post: (path, body) =>
      new Promise((resolve, reject) =>
        requests.push({ method: "POST", path, body, resolve, reject }),
      ),
    setLastSaved: () => {},
    setError: () => {},
    setAttempt: () => {},
  };
  for (const [setter, key] of Object.entries({
    setConfirm: "confirm",
    setReview: "review",
    setAllowMissing: "allowMissing",
    setReviewError: "reviewError",
    setReviewing: "reviewing",
    setSubmitting: "submitting",
    setDirty: "dirty",
  }))
    env[setter] = (value) => {
      state[key] = value;
    };
  const run = (name) => {
    const scope = {
      ...env,
      review: state.review,
      reviewing: state.reviewing,
      allowMissing: state.allowMissing,
    };
    return new Function(
      ...Object.keys(scope),
      `${compiled[name]}; return callback;`,
    )(...Object.values(scope))();
  };
  const reviewed = async (value = receipt()) => {
    const pending = run("beginReview");
    requests.at(-1).resolve({ saved: true });
    await flush();
    requests.at(-1).resolve(value);
    await pending;
  };
  return { env, state, requests, run, reviewed };
}
test("review waits for old autosave, then persists and reviews the same captured snapshot", async () => {
  const h = harness();
  let finishOldSave;
  h.env.savePending.current = new Promise((resolve) => {
    finishOldSave = resolve;
  });
  const pending = h.run("beginReview");
  assert.equal(h.requests.length, 0);
  h.env.answersRef.current.first[0].value = 99;
  finishOldSave();
  await flush();
  assert.deepEqual(h.requests[0].body.answers, { first: [{ value: 7 }] });
  assert.equal(h.requests.length, 1);
  h.requests[0].resolve({ saved: true });
  await flush();
  assert.equal(h.requests[1].path, "/assessments/synthetic-attempt/review");
  assert.strictEqual(h.requests[1].body.answers, h.requests[0].body.answers);
  h.requests[1].resolve(receipt());
  await pending;
  assert.strictEqual(h.state.review.answers, h.requests[0].body.answers);
  assert.equal(h.state.reviewing, false);
});
test("failed fresh save never calls review or permits final submit", async () => {
  const h = harness();
  const pending = h.run("beginReview");
  h.requests[0].reject(new Error("Draft could not be saved"));
  await pending;
  assert.equal(h.state.review, null);
  assert.equal(h.state.reviewing, false);
  assert.match(h.state.reviewError.message, /could not be saved/);
  await h.run("submit");
  assert.equal(h.requests.length, 1);
});
test("a blocked server receipt is retained for display but never submitted", async () => {
  const h = harness();
  await h.reviewed(
    receipt({
      structural_ready: false,
      issues: [{ item_id: "first", kind: "format", detail: "Malformed JSON" }],
      prospective_answers_sha256: null,
      review_token: null,
    }),
  );
  assert.equal(h.state.review.receipt.issues[0].detail, "Malformed JSON");
  assert.equal(h.state.reviewError, undefined);
  h.state.allowMissing = true;
  await h.run("submit");
  assert.equal(h.requests.length, 2);
});
test("missing answers need explicit consent and final submit uses the received token", async () => {
  const h = harness();
  await h.reviewed(
    receipt({
      answered: 0,
      structural_ready: false,
      issues: [{ item_id: "first", kind: "missing", detail: "No answer" }],
    }),
  );
  await h.run("submit");
  assert.equal(h.requests.length, 2);
  h.state.allowMissing = true;
  const pending = h.run("submit");
  assert.equal(h.requests[2].body.allow_incomplete, true);
  assert.equal(h.requests[2].body.review_token, digest);
  assert.strictEqual(h.requests[2].body.answers, h.state.review.answers);
  h.requests[2].resolve({
    id: "synthetic-attempt",
    items: [],
    result: { passed: false },
  });
  await pending;
  assert.equal(h.state.confirm, false);
});
test("stale review clears confirmation; a transport failure keeps the same token for idempotent retry", async () => {
  const h = harness();
  await h.reviewed();
  const first = h.run("submit");
  h.requests[2].reject(new Error("Response lost"));
  await first;
  assert.ok(h.state.review);
  const retry = h.run("submit");
  assert.deepEqual(h.requests[3].body, h.requests[2].body);
  h.requests[3].reject(new ApiError("REVIEW_STALE"));
  await retry;
  assert.equal(h.state.review, null);
  assert.equal(h.env.submittedRef.current, false);
});
test("a closed attempt during review refreshes its server state and closes the confirmation", async () => {
  const h = harness();
  const pending = h.run("beginReview");
  h.requests[0].reject(new ApiError("ATTEMPT_CLOSED"));
  await pending;
  assert.equal(h.state.loads, 1);
  assert.equal(h.state.confirm, false);
  assert.equal(h.env.reviewRef.current, false);
});

test("a late review response after generation cleanup cannot install a receipt", async () => {
  const h = harness();
  const pending = h.run("beginReview");
  h.requests[0].resolve({ saved: true });
  await flush();
  assert.equal(h.requests.length, 2);
  h.env.reviewGeneration.current++;
  h.requests[1].resolve(receipt());
  await pending;
  assert.equal(h.state.review, null);
  assert.equal(h.state.reviewError, undefined);
});

test("final submit sends captured answers instead of a mutable current draft and an invalid-answer response requires a new review", async () => {
  const h = harness();
  await h.reviewed();
  h.env.answersRef.current.first[0].value = 99;
  const pending = h.run("submit");
  assert.deepEqual(h.requests[2].body.answers, { first: [{ value: 7 }] });
  h.requests[2].reject(new ApiError("ASSESSMENT_ANSWER_INVALID"));
  await pending;
  assert.equal(h.state.review, null);
  await h.run("submit");
  assert.equal(h.requests.length, 3);
});

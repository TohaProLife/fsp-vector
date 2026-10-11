import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import ts from "typescript";
const source = await readFile(
  new URL("../src/lib/assessment-review.ts", import.meta.url),
  "utf8",
);
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    target: ts.ScriptTarget.ES2022,
    module: ts.ModuleKind.ES2022,
  },
}).outputText;
const {
  captureAnswers,
  answerPresent,
  validateReviewReceipt,
  reviewSubmissionAllowed,
  reviewedSubmitBody,
} = await import(
  `data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`
);
const digest = "a".repeat(64);
const receipt = (overrides = {}) => ({
  answered: 2,
  total: 2,
  structural_ready: true,
  issues: [],
  public_form_sha256: digest,
  saved_answers_sha256: digest,
  prospective_answers_sha256: digest,
  review_token: digest,
  limitations: ["Format only, no correctness preview"],
  ...overrides,
});
const review = (overrides = {}) => ({
  answers: captureAnswers({ first: [], second: 0 }),
  receipt: receipt(overrides),
  version: 4,
});

test("the reviewed JSON snapshot stays unchanged when the editable draft changes", () => {
  const draft = { first: [{ value: 7 }], second: {}, third: 0 };
  const snapshot = captureAnswers(draft);
  draft.first[0].value = 99;
  draft.first.push({ value: 100 });
  draft.second.new = true;
  assert.deepEqual(snapshot, { first: [{ value: 7 }], second: {}, third: 0 });
  assert.ok(Object.isFrozen(snapshot));
  assert.ok(Object.isFrozen(snapshot.first));
  assert.ok(Object.isFrozen(snapshot.first[0]));
});
test("unsupported JSON values are rejected rather than converted or silently omitted", () => {
  for (const value of [
    undefined,
    NaN,
    Infinity,
    -Infinity,
    1n,
    () => 1,
    Symbol("x"),
    new Date(),
    new Map(),
  ])
    assert.throws(() => captureAnswers({ first: value }));
  const cyclic = {};
  cyclic.loop = cyclic;
  assert.throws(() => captureAnswers(cyclic));
  assert.throws(() => captureAnswers({ first: new Array(2) }));
  assert.throws(() =>
    captureAnswers({
      first: Object.defineProperty({}, "hidden", { value: 1 }),
    }),
  );
  assert.throws(() =>
    captureAnswers({
      first: {
        get value() {
          throw new Error("must not execute");
        },
      },
    }),
  );
});
test("empty JSON containers and numeric zero are present, while whitespace and null are missing", () => {
  for (const value of [[], {}, 0, false, "[]", "{}", "select 0"])
    assert.equal(answerPresent(value), true);
  for (const value of [undefined, null, "", " \n\t "])
    assert.equal(answerPresent(value), false);
});
test("format and limit issues never become submittable through missing-answer opt-in", () => {
  for (const kind of ["format", "limit"])
    assert.equal(
      reviewSubmissionAllowed(
        review({
          structural_ready: false,
          issues: [{ item_id: "first", kind, detail: "Fix the answer" }],
        }),
        true,
      ),
      false,
    );
});
test("missing answers require a server receipt and explicit matching opt-in", () => {
  const incomplete = review({
    answered: 1,
    structural_ready: false,
    issues: [{ item_id: "second", kind: "missing", detail: "No answer" }],
  });
  assert.equal(reviewSubmissionAllowed(incomplete, false), false);
  assert.equal(reviewSubmissionAllowed(incomplete, true), true);
  assert.equal(reviewSubmissionAllowed(null, true), false);
  assert.equal(
    reviewSubmissionAllowed(
      review({
        answered: 0,
        structural_ready: false,
        issues: [
          {
            item_id: "second",
            kind: "missing",
            detail: "Inconsistent receipt",
          },
        ],
      }),
      true,
    ),
    false,
  );
});
test("final submission uses the immutable reviewed answers and token, without grading hints", () => {
  const complete = review();
  assert.deepEqual(reviewedSubmitBody(complete, true), {
    answers: { first: [], second: 0 },
    review_token: digest,
    allow_incomplete: false,
  });
  assert.throws(() =>
    reviewedSubmitBody(
      review({
        structural_ready: false,
        issues: [{ item_id: "first", kind: "format", detail: "Invalid JSON" }],
      }),
      true,
    ),
  );
});
test("an incomplete or malformed receipt fails closed", () => {
  for (const overrides of [
    { review_token: "" },
    { public_form_sha256: "not-a-hash" },
    { answered: 3 },
    { total: 0 },
    { structural_ready: undefined },
    { issues: null },
    { limitations: null },
  ]) {
    assert.throws(() => validateReviewReceipt(receipt(overrides)));
    assert.equal(reviewSubmissionAllowed(review(overrides), true), false);
  }
});

test("a legitimate blocked receipt with null hashes and a global issue remains displayable but cannot submit", () => {
  const blocked = review({
    structural_ready: false,
    issues: [
      { item_id: null, kind: "limit", detail: "Draft exceeds request limit" },
    ],
    public_form_sha256: null,
    saved_answers_sha256: null,
    prospective_answers_sha256: null,
    review_token: null,
  });
  assert.doesNotThrow(() => validateReviewReceipt(blocked.receipt));
  assert.equal(reviewSubmissionAllowed(blocked, true), false);
  assert.throws(() => reviewedSubmitBody(blocked, true));
});

test("a corrected prospective draft can submit when the prior malformed saved draft has no diagnostic hash", () => {
  const corrected = review({ saved_answers_sha256: null });
  assert.doesNotThrow(() => validateReviewReceipt(corrected.receipt));
  assert.equal(reviewSubmissionAllowed(corrected, false), true);
  assert.deepEqual(reviewedSubmitBody(corrected, false).answers, {
    first: [],
    second: 0,
  });
});

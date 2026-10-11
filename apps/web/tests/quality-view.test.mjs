import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import React from "react";
import * as runtime from "react/jsx-runtime";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";

const source = await readFile(
  new URL("../src/features/operations.tsx", import.meta.url),
  "utf8",
);
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    target: ts.ScriptTarget.ES2022,
    module: ts.ModuleKind.CommonJS,
    jsx: ts.JsxEmit.ReactJSX,
  },
}).outputText;
let response;
const ui = new Proxy(
  {},
  {
    get:
      (_target, name) =>
      ({ children, title, description }) =>
        React.createElement(
          name === "Badge" ? "span" : "section",
          null,
          title,
          description,
          children,
        ),
  },
);
const exports = {};
new Function("require", "exports", compiled)((name) => {
  if (name === "react") return React;
  if (name === "react/jsx-runtime") return runtime;
  if (name === "lucide-react") return new Proxy({}, { get: () => () => null });
  if (name === "@/lib/hooks")
    return {
      useResource: () => ({ data: response, loading: false, reload: () => {} }),
    };
  if (name === "@/lib/api")
    return {
      date: (value) => value ?? "Не указано",
      items: (data) => data?.items ?? [],
    };
  if (name === "@/components/ui") return ui;
  throw new Error(`Unexpected dependency ${name}`);
}, exports);
const measurements = {
  bank: { forms: 41, items: 492, failures: 0, families: 8 },
  retest: {
    protocol_id: "synthetic-fixture",
    pairs: 100,
    forms: 40,
    administrations: 200,
    agreement: 0.7351,
    attention_agreement: 0.4217,
    negative_item_rest: 53,
    nonpositive_separation: 2,
    undefined_correlations: 3,
    nonmonotonic_flags: 4,
  },
  matching_holdout: {
    queries: 71,
    labels: 440,
    precision5: 0.6152,
    ndcg10_end_to_end: 0.4987,
    ndcg10_eligible: 0.6876,
    retrieval_recall: 0.3521,
    gate_violations: 0,
    baselines: {
      random_eligible: { precision5: 0.1531, ndcg10_end_to_end: 0.2291 },
      keyword_all: { precision5: 0.3467, ndcg10_end_to_end: 0.4391 },
      strong_category_test: { precision5: 0.5321, ndcg10_end_to_end: 0.4841 },
      full_neutral: { precision5: 0.6721, ndcg10_end_to_end: 0.5221 },
    },
  },
};
function render(evaluation) {
  response = {
    runtime: {},
    counts: {},
    human_pilot: { sample_size: 0 },
    evaluation,
  };
  return renderToStaticMarkup(
    React.createElement(exports.Quality, { me: { role: "candidate" } }),
  );
}
test("ready quality measurements display the API values, attention group, negative diagnostics and controls separately", () => {
  const markup = render({
    status: "ready",
    measurements,
    generated_at: "fixture-date",
    provenance: {
      status: "verified",
      checked_files: 5,
      report_sha256: "a".repeat(64),
      stability_sha256: "b".repeat(64),
    },
  });
  for (const value of [
    "73,51",
    "42,17",
    "53",
    "0,4987",
    "0,6876",
    "35,21",
    "15,31",
    "34,67",
    "53,21",
    "67,21",
  ])
    assert.ok(markup.includes(value), value);
  assert.ok(markup.includes("не измерено"));
  assert.ok(markup.includes("Полнота после обязательных фильтров"));
  assert.ok(!markup.includes("Recall@10"));
  assert.ok(markup.includes("Это не"));
  assert.ok(!markup.includes("86,04"), "No hardcoded observed score fallback");
});
test("unavailable, stale, corrupt and invalid snapshots never render even supplied measurements", () => {
  for (const status of [
    "unavailable",
    "source_mismatch",
    "integrity_mismatch",
    "invalid_artifact",
  ]) {
    const markup = render({
      status,
      reason: `fixture-${status}`,
      measurements,
    });
    assert.ok(markup.includes(`fixture-${status}`));
    assert.ok(markup.includes("Числа скрыты"));
    assert.ok(!markup.includes("73,51"));
    assert.ok(!markup.includes("Пары повторных прохождений"));
  }
});
test("a ready status without measurements fails closed, while a missing scalar is not reported as zero", () => {
  assert.ok(
    render({ status: "ready", measurements: null }).includes("Числа скрыты"),
  );
  const markup = render({
    status: "ready",
    measurements: {
      ...measurements,
      retest: { ...measurements.retest, agreement: null },
    },
  });
  assert.ok(markup.includes("Совпадение категорий"));
  assert.ok(!markup.includes("73,51"));
  assert.ok(markup.includes("Не указано"));
});

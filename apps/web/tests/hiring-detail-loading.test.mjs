import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import ts from "typescript";
import React from "react";
import * as runtime from "react/jsx-runtime";
import { renderToStaticMarkup } from "react-dom/server";

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

function harness(component) {
  const declaration = file.statements.find(
    (node) => ts.isFunctionDeclaration(node) && node.name?.text === component,
  );
  const statement = declaration.body.statements.find(
    (node) =>
      ts.isVariableStatement(node) &&
      node.declarationList.declarations.some(
        (entry) => entry.name.getText(file) === "open",
      ),
  );
  const handler = statement.declarationList.declarations
    .find((entry) => entry.name.getText(file) === "open")
    .initializer.getText(file);
  const compiled = ts.transpileModule(`const open = ${handler};`, {
    compilerOptions: { target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const state = {
    detail: null,
    error: undefined,
    result: null,
    answer: "",
    reloads: 0,
  };
  const generation = { current: 0 };
  const requests = [];
  const api = (path) =>
    new Promise((resolve, reject) => requests.push({ path, resolve, reject }));
  const setDetail = (value) => {
    state.detail = typeof value === "function" ? value(state.detail) : value;
  };
  const setError = (value) => {
    state.error = value;
  };
  const open = new Function(
    "api",
    "detailGeneration",
    "setDetail",
    "setDetailError",
    "setActionError",
    "setResult",
    "setAnswer",
    "reload",
    `${compiled}; return open;`,
  )(
    api,
    generation,
    setDetail,
    setError,
    setError,
    (value) => {
      state.result = value;
    },
    (value) => {
      state.answer = value;
    },
    () => {
      state.reloads++;
    },
  );
  return {
    state,
    requests,
    open,
    close() {
      generation.current++;
      state.detail = null;
      state.error = undefined;
    },
  };
}

function privateViews(data) {
  const compiled = ts.transpileModule(source, {
    compilerOptions: {
      target: ts.ScriptTarget.ES2022,
      module: ts.ModuleKind.CommonJS,
      jsx: ts.JsxEmit.ReactJSX,
    },
  }).outputText;
  const ui = new Proxy(
    {},
    {
      get:
        (_target, name) =>
        ({ children, title, description }) =>
          React.createElement(
            name === "Button" ? "button" : "section",
            null,
            title,
            description,
            children,
          ),
    },
  );
  const exports = {};
  new Function(
    "require",
    "exports",
    `${compiled}; exports.privateViews = { ChallengeReview, InvitationDetail };`,
  )((name) => {
    if (name === "react")
      return { ...React, useState: (initial) => [initial, () => {}] };
    if (name === "react/jsx-runtime") return runtime;
    if (name === "lucide-react")
      return new Proxy({}, { get: () => () => null });
    if (name === "@/lib/hooks")
      return {
        useResource: () => ({ data, loading: false, reload: () => {} }),
      };
    if (name === "@/lib/api")
      return {
        specLabels: {},
        items: (value) => value?.items ?? [],
        money: (value) => value ?? "—",
        date: (value) => value ?? "—",
        statusName: (value) => value ?? "—",
        safeURL: () => null,
      };
    if (name === "@/components/ui") return ui;
    if (
      ["./code-practice", "./need-practice", "@/lib/assessment-scope"].includes(
        name,
      )
    )
      return {};
    throw new Error(`Unexpected dependency ${name}`);
  }, exports);
  return exports.privateViews;
}
test("historical redacted challenge content shows the privacy boundary and exposes no answer or review form", () => {
  const { ChallengeReview } = privateViews({
    items: [
      {
        id: "blocked",
        candidate: { alias: "Synthetic" },
        content_redacted: true,
        private_content_available: false,
        privacy_reason: "company_blocked",
        answer: "MUST_NOT_RENDER_PRIVATE_ANSWER",
        result: { status: "content_unavailable" },
      },
    ],
  });
  const markup = renderToStaticMarkup(
    React.createElement(ChallengeReview, {
      challengeId: "task",
      onClose: () => {},
      notify: () => {},
    }),
  );
  assert.ok(markup.includes("Содержание закрыто"));
  assert.ok(markup.includes("заблокировал компанию"));
  assert.ok(!markup.includes("MUST_NOT_RENDER_PRIVATE_ANSWER"));
  assert.ok(!markup.includes("<form"));
});
test("available employer challenge observations retain their actual answer and manual review form", () => {
  const { ChallengeReview } = privateViews({
    items: [
      {
        id: "available",
        candidate: { alias: "Synthetic" },
        content_redacted: false,
        private_content_available: true,
        answer: "SAFE_AVAILABLE_ANSWER",
        result: { status: "pending_review" },
      },
    ],
  });
  const markup = renderToStaticMarkup(
    React.createElement(ChallengeReview, {
      challengeId: "task",
      onClose: () => {},
      notify: () => {},
    }),
  );
  assert.ok(markup.includes("SAFE_AVAILABLE_ANSWER"));
  assert.ok(markup.includes("<form"));
});
test("redacted candidate messages keep timestamps and notice while the employer's own terms remain visible", () => {
  const { InvitationDetail } = privateViews(null);
  const markup = renderToStaticMarkup(
    React.createElement(InvitationDetail, {
      invitation: {
        id: "invite",
        status: "accepted",
        content_redacted: true,
        privacy_reason: "processing_withdrawn",
        company: { name: "Synthetic company" },
        messages: [
          {
            id: "candidate",
            text: "MUST_NOT_RENDER_PRIVATE_MESSAGE",
            content_redacted: true,
            created_at: "fixture-date",
            author_role: "candidate",
          },
          {
            id: "company",
            text: "SAFE_COMPANY_TERMS",
            content_redacted: false,
            author_role: "employer",
          },
        ],
      },
      employer: true,
      onClose: () => {},
      onRetry: () => {},
      onUpdated: () => {},
    }),
  );
  assert.ok(markup.includes("Содержание закрыто"));
  assert.ok(markup.includes("fixture-date"));
  assert.ok(markup.includes("SAFE_COMPANY_TERMS"));
  assert.ok(!markup.includes("MUST_NOT_RENDER_PRIVATE_MESSAGE"));
});

for (const component of ["Invitations", "Practice"]) {
  test(`${component}: a failed detail read ends loading and a deliberate retry recovers`, async () => {
    const h = harness(component);
    const failed = h.open({ id: "synthetic-item", title: "Card" });
    assert.equal(h.state.detail._loading, true);
    const denied = new Error("404: item no longer available");
    h.requests[0].reject(denied);
    await failed;
    assert.equal(h.state.error, denied);
    assert.equal(h.state.detail._loading, false);
    if (component === "Practice")
      assert.equal(h.state.detail._loadFailed, true);
    const retry = h.open(h.state.detail);
    assert.equal(h.state.error, undefined);
    assert.equal(h.state.detail._loading, true);
    h.requests[1].resolve({
      id: "synthetic-item",
      status: "pending",
      description: "Full safe DTO",
    });
    await retry;
    assert.equal(h.state.detail._loading, undefined);
    assert.equal(h.state.detail._loadFailed, undefined);
    assert.equal(h.state.detail.id, "synthetic-item");
  });
  test(`${component}: a closed detail cannot be reopened by its late request`, async () => {
    const h = harness(component);
    const pending = h.open({ id: "closed" });
    h.close();
    h.requests[0].resolve({ id: "closed", description: "Late response" });
    await pending;
    assert.equal(h.state.detail, null);
    assert.equal(h.state.error, undefined);
    assert.equal(h.state.reloads, 0);
  });
  test(`${component}: an older failure cannot overwrite a newer selected detail`, async () => {
    const h = harness(component);
    const old = h.open({ id: "old" });
    const selected = h.open({ id: "selected" });
    h.requests[1].resolve({ id: "selected", description: "Current response" });
    await selected;
    h.requests[0].reject(new Error("Old request failure"));
    await old;
    assert.equal(h.state.detail.id, "selected");
    assert.equal(h.state.error, undefined);
  });
}

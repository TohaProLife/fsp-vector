import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import ts from "typescript";
import React from "react";
import * as runtime from "react/jsx-runtime";
import { renderToStaticMarkup } from "react-dom/server";

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
const declarations = ["HistoryPage", "HistoryPagination"].map((name) =>
  file.statements
    .find((node) => ts.isFunctionDeclaration(node) && node.name?.text === name)
    .getText(file)
    .replace(/^export\s+/, ""),
);
const compiled = ts.transpileModule(declarations.join("\n"), {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022,
    jsx: ts.JsxEmit.ReactJSX,
  },
}).outputText;

function harness({
  tab = "attempts",
  stalePage = false,
  error = undefined,
} = {}) {
  const state = [1, 1, tab];
  const paths = [];
  let hook = 0;
  const primitive =
    (name) =>
    ({ children, title, text, description, action, variant, ...props }) =>
      React.createElement(
        name,
        props,
        title,
        text,
        description,
        children,
        action,
      );
  const resource = (path) => {
    paths.push(path);
    const page = Number(
      new URL(path, "http://test.local").searchParams.get("page"),
    );
    const survey = path.startsWith("/candidate/survey-history");
    const count = page === 1 ? 30 : page === 2 ? 10 : 0;
    return {
      loading: false,
      error: survey ? undefined : error,
      reload: () => {},
      data: {
        total: 40,
        page: stalePage ? 1 : page,
        page_size: 30,
        items: Array.from({ length: count }, (_, index) => ({
          id: `${survey ? "survey" : "attempt"}-${(page - 1) * 30 + index}`,
          specialization: "backend",
          grade: "middle",
          status: "expired",
          started_at: "fixture-date",
          created_at: "fixture-date",
          snapshot_available: true,
          answers: {
            specialization: "backend",
            grade: "middle",
            work_format: "remote",
            industry: "product",
            stack: ["SQL"],
          },
        })),
      },
    };
  };
  const env = {
    exports: {},
    require: () => runtime,
    useState: (initial) => {
      const index = hook++;
      return [
        state[index] ?? initial,
        (value) => {
          state[index] = value;
        },
      ];
    },
    useResource: resource,
    items: (value) => value?.items ?? [],
    PageTitle: primitive("header"),
    Link: primitive("a"),
    Button: primitive("button"),
    Tag: primitive("span"),
    Badge: primitive("span"),
    Empty: primitive("section"),
    Loading: primitive("section"),
    ErrorBox: primitive("section"),
    ArrowRight: () => null,
    specName: (value) => value,
    gradeName: (value) => value,
    date: (value) => value,
    formats: [["remote", "Удалённо"]],
    assessmentKind: () => "global_category",
    assessmentStatus: (value) => value.status,
  };
  const HistoryPage = new Function(
    ...Object.keys(env),
    `${compiled}; return HistoryPage;`,
  )(...Object.values(env));
  const render = () => {
    hook = 0;
    return HistoryPage({});
  };
  function expand(node) {
    if (!React.isValidElement(node)) return node;
    if (typeof node.type === "function") return expand(node.type(node.props));
    const children = React.Children.toArray(node.props.children).map(expand);
    return React.cloneElement(node, node.props, ...children);
  }
  const nodes = (node) =>
    React.isValidElement(node)
      ? [node, ...React.Children.toArray(node.props.children).flatMap(nodes)]
      : [];
  const tree = () => expand(render());
  const click = (text) => {
    const node = nodes(tree()).find(
      (element) =>
        element.type === "button" &&
        React.Children.toArray(element.props.children).includes(text),
    );
    assert.ok(node, `Missing button ${text}`);
    assert.equal(node.props.disabled, false, `${text} must be actionable`);
    node.props.onClick();
  };
  return {
    state,
    paths,
    tree,
    click,
    markup: () => renderToStaticMarkup(tree()),
  };
}

for (const tab of ["attempts", "surveys"]) {
  test(`History ${tab}: next and previous request the actual server page, showing the API total`, () => {
    const h = harness({ tab });
    assert.match(h.markup(), /Показано 1–30 из 40/);
    h.click("Следующая");
    const markup = h.markup();
    assert.match(markup, /Показано 31–40 из 40/);
    assert.ok(
      h.paths.includes(
        `/candidate/${tab === "attempts" ? "history" : "survey-history"}?page=2&page_size=30`,
      ),
    );
    assert.ok(
      !markup.includes(`${tab === "attempts" ? "attempt" : "survey"}-0`),
    );
    h.click("Предыдущая");
    assert.match(h.markup(), /Показано 1–30 из 40/);
  });
}

test("History: changing page hides the previous page DTO until the requested page arrives", () => {
  const h = harness({ stalePage: true });
  h.click("Следующая");
  const markup = h.markup();
  assert.match(markup, /Загружаем попытки/);
  assert.ok(!markup.includes("Показано 31–40"));
});

test("History: a failed attempts read does not prevent reading independent survey history", () => {
  const h = harness({
    tab: "surveys",
    error: new Error("Attempt read failed"),
  });
  const markup = h.markup();
  assert.match(markup, /Опрос сам по себе не подтверждает грейд/);
  assert.match(markup, /Показано 1–30 из 40/);
});

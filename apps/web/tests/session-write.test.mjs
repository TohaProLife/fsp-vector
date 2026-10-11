import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import ts from "typescript";

const source = await readFile(
  new URL("../src/lib/api.ts", import.meta.url),
  "utf8",
);
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    target: ts.ScriptTarget.ES2022,
    module: ts.ModuleKind.ES2022,
  },
}).outputText;
let instance = 0;
const coldPage = () =>
  import(
    `data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}#page-${++instance}`
  );
const response = (data, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });

test("a restored standalone page sends its first mutation with the live session CSRF", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", async (url, options) => {
    calls.push({ url, options });
    return url.endsWith("/auth/me")
      ? response({ csrf_token: "synthetic-session-csrf" })
      : response({ status: "completed" });
  });
  const client = await coldPage();
  await client.post("/assessments/synthetic-attempt/submit", { answers: {} });
  assert.equal(calls.length, 2);
  assert.equal(calls[0].url, "/api/v1/auth/me");
  assert.equal(calls[1].url, "/api/v1/assessments/synthetic-attempt/submit");
  assert.equal(
    calls[1].options.headers.get("X-CSRF-Token"),
    "synthetic-session-csrf",
  );
  assert.equal(calls[1].options.credentials, "same-origin");
  assert.equal(calls[1].options.cache, "no-store");
});

test("a session refresh failure prevents a protected mutation", async (t) => {
  const urls = [];
  t.mock.method(globalThis, "fetch", async (url) => {
    urls.push(url);
    return response(
      { code: "AUTH_REQUIRED", detail: "Войдите в аккаунт." },
      401,
    );
  });
  const client = await coldPage();
  await assert.rejects(
    client.post("/assessments/synthetic-attempt/submit", { answers: {} }),
    (error) => error.status === 401 && error.code === "AUTH_REQUIRED",
  );
  assert.deepEqual(urls, ["/api/v1/auth/me"]);
});

test("concurrent cold-page writes share one refresh and all carry the token", async (t) => {
  const calls = [];
  t.mock.method(globalThis, "fetch", async (url, options) => {
    calls.push({ url, options });
    await Promise.resolve();
    return response(
      url.endsWith("/auth/me")
        ? { csrf_token: "synthetic-session-csrf" }
        : { ok: true },
    );
  });
  const client = await coldPage();
  await Promise.all([
    client.put("/assessments/synthetic-attempt/answers", { answers: {} }),
    client.post("/candidate/contact-grants/synthetic-grant/revoke"),
  ]);
  assert.equal(calls.filter((call) => call.url.endsWith("/auth/me")).length, 1);
  for (const call of calls.filter((call) => !call.url.endsWith("/auth/me")))
    assert.equal(
      call.options.headers.get("X-CSRF-Token"),
      "synthetic-session-csrf",
    );
});

test("anonymous registration works without requesting an existing session", async (t) => {
  const urls = [];
  t.mock.method(globalThis, "fetch", async (url) => {
    urls.push(url);
    return response({ registered: true }, 201);
  });
  const client = await coldPage();
  await client.post("/auth/register", { email: "synthetic@vector.local" });
  assert.deepEqual(urls, ["/api/v1/auth/register"]);
});

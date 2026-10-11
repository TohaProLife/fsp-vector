import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import ts from "typescript";

const source = await readFile(
  new URL("../src/lib/assessment-scope.ts", import.meta.url),
  "utf8",
);
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    target: ts.ScriptTarget.ES2022,
    module: ts.ModuleKind.ES2022,
  },
}).outputText;
const {
  assessmentKind,
  assessmentStatus,
  certifiesGrade,
  needStartBody,
  weeklyState,
  availabilityState,
} = await import(
  `data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`
);

test("passed company practice is a practice result and never a confirmed global grade", () => {
  const record = {
    scope: "employer_need_practice",
    status: "completed",
    certifies_global_category: false,
    result: {
      passed: true,
      confirmed_grade: null,
      global_confirmed_grade: "junior",
    },
  };
  assert.equal(assessmentKind(record), "need_practice");
  assert.equal(certifiesGrade(record), false);
  assert.equal(
    certifiesGrade({
      ...record,
      result: { passed: true, confirmed_grade: "senior" },
    }),
    false,
  );
  assert.equal(assessmentStatus(record), "Практика выполнена");
  assert.equal(
    assessmentKind({
      result: { scope: "employer_need_practice", passed: true },
    }),
    "need_practice",
  );
  assert.equal(
    assessmentStatus({ ...record, result: { passed: false } }),
    "Практика не пройдена",
  );
  assert.equal(
    assessmentStatus({ ...record, status: "expired" }),
    "Время истекло",
  );
});

test("demo pass is explicitly separated from persisted category confirmation", () => {
  assert.equal(
    assessmentStatus({
      status: "completed",
      demo: true,
      result: { passed: true },
    }),
    "Демонстрация завершена",
  );
  assert.equal(
    certifiesGrade({
      demo: true,
      result: { passed: true, confirmed_grade: "senior" },
    }),
    false,
  );
  assert.equal(
    certifiesGrade({
      scope: "global_category",
      certifies_global_category: false,
      result: { passed: true, confirmed_grade: "senior" },
    }),
    false,
  );
  assert.equal(
    certifiesGrade({
      scope: "global_category",
      result: { passed: true, confirmed_grade: null },
    }),
    false,
  );
  assert.equal(
    assessmentStatus({
      status: "completed",
      scope: "global_category",
      result: { passed: true, confirmed_grade: "middle" },
    }),
    "Подтверждён",
  );
});

test("need practice request contains exactly one authorized source ID, never an arbitrary need ID", () => {
  assert.deepEqual(needStartBody({ invitationId: "inv-1" }), {
    invitation_id: "inv-1",
  });
  assert.deepEqual(needStartBody({ vacancyId: "job-2" }), {
    vacancy_id: "job-2",
  });
  assert.throws(() => needStartBody({}));
  assert.throws(() => needStartBody({ invitationId: " ", vacancyId: " " }));
  assert.throws(() =>
    needStartBody({ invitationId: "inv-1", vacancyId: "job-2" }),
  );
});

test("server cooldown blocks a new formal attempt but permits resuming the exact active route", () => {
  const base = {
    specialization: "backend",
    items: [
      {
        grade: "junior",
        allowed: false,
        next_allowed_at: "2026-12-01T00:00:00Z",
      },
    ],
  };
  assert.equal(availabilityState(base, "backend", "junior").allowed, false);
  const active = {
    ...base,
    active_attempt: {
      id: "a1",
      specialization: "backend",
      grade: "junior",
      scope: "global_category",
    },
  };
  assert.equal(availabilityState(active, "backend", "junior").resumeId, "a1");
  assert.equal(availabilityState(active, "backend", "middle").allowed, false);
  assert.equal(
    availabilityState(
      {
        ...active,
        active_attempt: {
          ...active.active_attempt,
          scope: "employer_need_practice",
        },
      },
      "backend",
      "junior",
    ).conflict,
    true,
  );
});

test("stale availability from another specialization fails closed during route change", () => {
  const stale = {
    specialization: "backend",
    items: [{ grade: "junior", allowed: true }],
  };
  assert.equal(availabilityState(stale, "frontend", "junior").ready, false);
  assert.equal(availabilityState(stale, "frontend", "junior").allowed, false);
  assert.equal(availabilityState(null, "backend", "junior").allowed, false);
});

test("weekly view respects server repeat and opening instants, while completion remains a persisted state", () => {
  const now = Date.parse("2026-10-07T10:00:00Z");
  assert.equal(
    weeklyState({ retry_at: "2026-10-08T10:00:00Z" }, now).retryBlocked,
    true,
  );
  assert.equal(
    weeklyState({ retry_at: "2026-10-07T10:00:00Z" }, now).retryBlocked,
    false,
  );
  assert.equal(
    weeklyState({ opens_at: "2026-10-08T10:00:00Z" }, now).notOpen,
    true,
  );
  assert.equal(weeklyState({ completed: true }, now).completed, true);
  assert.equal(weeklyState({}, now).completed, false);
});

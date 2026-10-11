"use client";
import { useEffect, useState, useRef } from "react";
import { ShieldCheck, Play, LockKeyhole, RefreshCw } from "lucide-react";
import { post, Dict, items, date } from "@/lib/api";
import { useResource } from "@/lib/hooks";
import {
  Button,
  Field,
  Loading,
  ErrorBox,
  Notice,
  Badge,
  Empty,
} from "@/components/ui";
import type { WorkspaceContext } from "@/components/workspace";
export function CodePractice(ctx: WorkspaceContext) {
  const status = useResource<Dict>("/judge/status");
  const tasks = useResource<Dict>("/judge/tasks");
  const history = useResource<Dict>("/judge/submissions");
  const [taskId, setTaskId] = useState("");
  const [language, setLanguage] = useState("python");
  const [source, setSource] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [result, setResult] = useState<Dict | null>(null);
  const submitting = useRef(false);
  const list = items(tasks.data);
  const selected = list.find((t) => t.id === taskId);
  useEffect(() => {
    if (list.length && !taskId) setTaskId(list[0].id);
  }, [tasks.data, taskId]);
  const available = status.data?.available === true;
  if (status.loading || tasks.loading)
    return (
      <section className="linear-section v-practice">
        <h2>Практика программирования</h2>
        <Loading label="Проверяем подключение изолированной среды" />
      </section>
    );
  if (status.error !== undefined || tasks.error !== undefined)
    return (
      <section className="linear-section v-practice">
        <h2>Практика программирования</h2>
        <ErrorBox error={status.error || tasks.error} />
      </section>
    );
  return (
    <div className="linear-section v-practice">
      <div className="v-practice-status">
        <Notice tone={available ? "green" : "amber"}>
          {available
            ? "Изолированная среда подключена. Решение проверяется отдельно, с ограничениями времени и ресурсов."
            : "Изолированная среда сейчас недоступна. Можно выбрать соседнюю вкладку и решать безопасные задачи с SQL и структурированными данными."}
        </Notice>
      </div>
      <div className="linear-detail-layout v-detail-layout">
        <div className="linear-detail-main v-detail-main">
          <div className="panel-header">
            <h2>Практика программирования</h2>
            <Badge tone={available ? "green" : "amber"}>
              {available ? "Среда подключена" : "Среда недоступна"}
            </Badge>
          </div>
          {list.length ? (
            <form
              className="form-stack v-practice-form"
              onSubmit={async (e) => {
                e.preventDefault();
                if (!available || submitting.current) return;
                submitting.current = true;
                setBusy(true);
                setError(undefined);
                try {
                  const r = await post("/judge/submissions", {
                    task_id: taskId,
                    language,
                    source,
                  });
                  setResult(r.result || r);
                  await history.reload();
                  ctx.notify("Решение проверено в изолированной среде");
                } catch (err) {
                  setError(err);
                } finally {
                  submitting.current = false;
                  setBusy(false);
                }
              }}
            >
              <Field label="Задание">
                <select
                  value={taskId}
                  disabled={busy}
                  onChange={(e) => {
                    setTaskId(e.target.value);
                    setResult(null);
                  }}
                >
                  {list.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.title}
                    </option>
                  ))}
                </select>
              </Field>
              <div className="question-prompt v-practice-prompt">
                {selected?.prompt}
              </div>
              {selected?.examples && (
                <details>
                  <summary>Публичные примеры</summary>
                  <pre className="code-input code-example">
                    {JSON.stringify(selected.examples, null, 2)}
                  </pre>
                </details>
              )}
              <Field label="Язык решения">
                <select
                  value={language}
                  disabled={busy}
                  onChange={(e) => setLanguage(e.target.value)}
                >
                  {(selected?.languages || ["python", "javascript"]).map(
                    (l: string) => (
                      <option value={l} key={l}>
                        {l === "python" ? "Python" : "JavaScript"}
                      </option>
                    ),
                  )}
                </select>
              </Field>
              <Field
                label="Исходный код"
                hint="Контракт ввода и вывода указан в условии. Не включай секреты или реальные данные."
              >
                <textarea
                  className="code-input v-code-editor"
                  spellCheck={false}
                  value={source}
                  disabled={busy}
                  onChange={(e) => setSource(e.target.value)}
                  maxLength={50000}
                  placeholder={
                    language === "python"
                      ? "# Напиши решение по контракту задачи"
                      : "// Напиши решение по контракту задачи"
                  }
                />
              </Field>
              {error !== undefined && <ErrorBox error={error} />}
              <div className="v-form-actions">
                <Button
                  type="submit"
                  busy={busy}
                  disabled={!available || !source.trim()}
                >
                  <Play size={15} />
                  {available
                    ? "Проверить в изолированной среде"
                    : "Для проверки нужна изолированная среда"}
                </Button>
              </div>
              {result && (
                <section
                  className="linear-section v-practice-result"
                  aria-live="polite"
                >
                  <h3>
                    {result.passed
                      ? "Публичные и скрытые проверки пройдены"
                      : "Результат проверки"}
                  </h3>
                  <dl className="linear-properties v-property-list">
                    <div className="linear-property-row v-property-row">
                      <dt>Статус</dt>
                      <dd>{result.status}</dd>
                    </div>
                    <div className="linear-property-row v-property-row">
                      <dt>Проверки</dt>
                      <dd>
                        {result.passed_cases ?? "—"} /{" "}
                        {result.total_cases ?? "—"}
                      </dd>
                    </div>
                    <div className="linear-property-row v-property-row">
                      <dt>Время</dt>
                      <dd>{result.elapsed_ms ?? "—"} мс</dd>
                    </div>
                    <div className="linear-property-row v-property-row">
                      <dt>Изоляция</dt>
                      <dd>{result.isolation || "—"}</dd>
                    </div>
                  </dl>
                  <small className="muted">
                    Этот результат не меняет категорию.
                  </small>
                </section>
              )}
            </form>
          ) : (
            <Empty
              title="Нет доступных задач"
              text="Подключённая среда ещё не предоставила задачи. Можно перейти к практике с данными."
            />
          )}
        </div>
        <aside className="linear-column v-inspector">
          <div className="panel">
            <div className="panel-header">
              <h2>Границы проверки</h2>
              <ShieldCheck size={19} className="purple" />
            </div>
            <p>
              Исходный код передаётся отдельно настроенному runner. API и
              Windows-host не исполняют его. Изоляция, доступность и режим
              запуска показываются по фактическому состоянию сервера.
            </p>
            <Notice>
              Практика не подтверждает весь грейд. Изменить категорию можно
              только через полноценный экзамен.
            </Notice>
            <div className="safe-data-note">
              <LockKeyhole size={14} />
              История решений доступна только своему аккаунту.
            </div>
          </div>
          <div className="panel">
            <div className="panel-header">
              <h2>История решений</h2>
              <Button
                variant="ghost"
                onClick={() => void history.reload()}
                aria-label="Обновить историю"
              >
                <RefreshCw size={14} />
              </Button>
            </div>
            {history.loading ? (
              <Loading label="Загружаем историю решений" />
            ) : history.error !== undefined ? (
              <ErrorBox error={history.error} />
            ) : items(history.data).length ? (
              items(history.data)
                .slice(0, 8)
                .map((s) => (
                  <div
                    className="linear-record-row v-record v-record-preview"
                    key={s.id}
                  >
                    <div className="v-record-content">
                      <strong>
                        {s.task_title ||
                          list.find((t) => t.id === s.task_id)?.title ||
                          s.task_id}
                      </strong>
                      <small className="v-record-meta">
                        {date(s.created_at)} · {s.language}
                      </small>
                    </div>
                    <div className="v-record-status">
                      <Badge tone={s.result?.passed ? "green" : "neutral"}>
                        {s.result?.status || s.status}
                      </Badge>
                    </div>
                  </div>
                ))
            ) : (
              <Empty
                title="Решений пока нет"
                text="После подключения среды и отправки кода здесь появится сохранённая проверка."
              />
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}

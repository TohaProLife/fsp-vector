"use client";
import { useState } from "react";
import {
  ShieldCheck,
  Database,
  Webhook,
  Check,
  RefreshCw,
  ArrowRight,
} from "lucide-react";
import { post, Dict, items, date } from "@/lib/api";
import { useResource } from "@/lib/hooks";
import {
  PageTitle,
  Button,
  Loading,
  ErrorBox,
  Notice,
  Badge,
  Empty,
} from "@/components/ui";
import type { WorkspaceContext } from "@/components/workspace";
export function IdentityPrivacy(ctx: WorkspaceContext) {
  const state = useResource<Dict>("/auth/consents");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [confirmRevoke, setConfirmRevoke] = useState(false);
  if (state.loading) return <Loading />;
  if (state.error !== undefined) return <ErrorBox error={state.error} />;
  const granted = state.data?.consent_processing;
  return (
    <>
      <PageTitle
        eyebrow="Прозрачное начало"
        title="Согласие на обработку"
        description="Это отдельное решение. Публикация профиля и открытие контактов управляются позже."
      />
      <div className="linear-detail-layout linear-settings v-operations v-consent-layout">
        <div className="linear-detail-main">
          <div className="panel-header">
            <h2>
              {granted ? "Согласие действует" : "Начнём с твоего согласия"}
            </h2>
            <ShieldCheck className="purple" size={22} />
          </div>
          <p>
            Платформа обрабатывает данные аккаунта, профессиональный профиль,
            результаты проверки навыков и историю взаимодействий для организации
            ИТ-найма. Данные сохраняются в локальном демонстрационном стенде.
            Используй вымышленные данные.
          </p>
          <Notice>
            Согласие можно отозвать. Без него профессиональные операции
            недоступны. Отзыв кандидатом скрывает профиль и закрывает дальнейший
            доступ компаний.
          </Notice>
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              if (granted && !confirmRevoke) {
                setConfirmRevoke(true);
                return;
              }
              setBusy(true);
              setError(undefined);
              try {
                await post("/auth/consents", { consent_processing: !granted });
                ctx.notify(
                  granted
                    ? "Согласие отозвано"
                    : "Согласие на обработку сохранено",
                );
                ctx.refresh();
                await state.reload();
              } catch (err) {
                setError(err);
              } finally {
                setBusy(false);
              }
            }}
            className="form-stack top-gap"
          >
            {!granted && (
              <label className="check-label">
                <input type="checkbox" required />
                <span>
                  Даю отдельное согласие на обработку данных для работы
                  платформы.
                </span>
              </label>
            )}
            {error !== undefined && <ErrorBox error={error} />}
            {confirmRevoke && (
              <Notice tone="amber">
                Подтверди отзыв: профессиональные операции остановятся до нового
                согласия.{" "}
                <button
                  className="link-action"
                  type="button"
                  onClick={() => setConfirmRevoke(false)}
                >
                  Отмена
                </button>
              </Notice>
            )}
            <div>
              <Button
                busy={busy}
                type="submit"
                variant={granted ? "secondary" : "primary"}
              >
                {granted
                  ? confirmRevoke
                    ? "Подтвердить отзыв"
                    : "Отозвать согласие"
                  : "Дать согласие и продолжить"}
                {!granted && <ArrowRight size={15} />}
              </Button>
            </div>
          </form>
        </div>
        <aside className="linear-properties">
          <h2>Свойства согласия</h2>
          <div className="list-row">
            <span>Обработка данных</span>
            <Badge tone={granted ? "green" : "neutral"}>
              {granted ? "Разрешена" : "Не разрешена"}
            </Badge>
          </div>
          <div className="list-row">
            <span>Хранилище</span>
            <span>Локальный стенд</span>
          </div>
          <Notice>
            Публикация профиля и разрешение конкретной компании на контакты —
            отдельные решения.
          </Notice>
        </aside>
      </div>
    </>
  );
}
export function Quality(ctx: WorkspaceContext) {
  const { data, error, loading, reload } =
    useResource<Dict>("/quality/summary");
  if (loading) return <Loading />;
  if (error !== undefined)
    return <ErrorBox error={error} retry={() => void reload()} />;
  if (!data) return null;
  const runtime = data.runtime || {};
  const counts = data.counts || {};
  const evaluation = data.evaluation || {};
  const measurements =
    evaluation.status === "ready" ? evaluation.measurements : null;
  const measurementStatus: Record<string, string> = {
    ready: "Авторский снимок проверен",
    unavailable: "Отчёт недоступен",
    integrity_mismatch: "Целостность снимка не подтверждена",
    source_mismatch: "Исходники изменились после измерения",
    invalid_artifact: "Артефакт измерения повреждён",
  };
  const metric = (value: unknown, percent = false) =>
    typeof value === "number" && Number.isFinite(value)
      ? new Intl.NumberFormat("ru-RU", {
          style: percent ? "percent" : "decimal",
          maximumFractionDigits: percent ? 2 : 4,
        }).format(value)
      : "Не указано";
  return (
    <>
      <PageTitle
        eyebrow="Локальный контроль качества"
        title="Основания и ограничения"
        description="Факты текущего стенда. Человеческая валидность и синтетические проверки показаны отдельно."
        action={
          <Button variant="secondary" onClick={() => void reload()}>
            <RefreshCw size={14} /> Обновить
          </Button>
        }
      />
      <div className="linear-detail-layout v-operations">
        <div className="linear-detail-main">
          <Notice tone="amber">
            Человеческий пилот не измерен. Наличие работающего экзамена и
            синтетических профилей не доказывает соответствие грейдов реальному
            рынку.
          </Notice>
          <div className="linear-stat-list top-gap">
            {[
              ["Профилей в базе", counts.candidates],
              ["Попыток экзамена", counts.attempts],
              ["Сохранённых подборок", counts.match_runs],
              ["Приглашений", counts.invitations],
            ].map(([label, value]) => (
              <div className="list-row" key={String(label)}>
                <span>{label}</span>
                <strong>{value ?? "—"}</strong>
              </div>
            ))}
          </div>
          <div className="v-measurement-sections">
            <div className="linear-section">
              <div className="panel-header">
                <h2>Проверка уровня</h2>
                <ShieldCheck size={18} className="purple" />
              </div>
              <div className="list-row">
                <div>
                  <strong>Шкала оценки</strong>
                  <small>Начальная рубрика авторов</small>
                </div>
                <Badge tone="amber">{data.calibration_status}</Badge>
              </div>
              <div className="list-row">
                <div>
                  <strong>Человеческий пилот</strong>
                  <small>
                    {data.human_pilot?.sample_size || 0} участников измерено
                  </small>
                </div>
                <Badge tone="amber">Не измерен</Badge>
              </div>
              <p className="safe-data-note">
                Сопоставимость форм, тест–ретест и связь с профессиональным
                грейдом требуют независимого человеческого исследования.
              </p>
            </div>
            <div className="linear-section">
              <div className="panel-header">
                <h2>Среда выполнения</h2>
                <Database size={18} className="purple" />
              </div>
              <div className="list-row">
                <div>
                  <strong>Хранилище</strong>
                  <small>Текущая подключённая база</small>
                </div>
                <Badge tone="green">{runtime.database}</Badge>
              </div>
              <div className="list-row">
                <div>
                  <strong>Исполнение пользовательского кода</strong>
                  <small>Windows-host пользовательский код не исполняет</small>
                </div>
                <Badge tone="amber">
                  {runtime.judge?.includes("unavailable")
                    ? "Недоступно · fail closed"
                    : runtime.judge}
                </Badge>
              </div>
              <div className="list-row">
                <div>
                  <strong>LLM API</strong>
                  <small>Основной путь без обязательного API</small>
                </div>
                <Badge>
                  {runtime.llm_required ? "Требуется" : "Не требуется"}
                </Badge>
              </div>
              <div className="list-row">
                <div>
                  <strong>Почта</strong>
                  <small>Явная демонстрационная доставка</small>
                </div>
                <Badge>{runtime.mail}</Badge>
              </div>
            </div>
          </div>
          <div className="linear-section top-gap v-measurement-section">
            <div className="panel-header">
              <h2>Синтетические измерения</h2>
              <Badge tone={measurements ? "purple" : "amber"}>
                {measurementStatus[evaluation.status] ||
                  "Нет проверенного отчёта"}
              </Badge>
            </div>
            <Notice tone="amber">
              Проверка SHA подтверждает целостность авторского снимка. Это не
              независимая экспертиза и не человеческая калибровка грейдов.
            </Notice>
            {!measurements ? (
              <Notice tone="amber">
                Числа скрыты до проверки происхождения и актуальности отчёта.
                {evaluation.reason && <p>{String(evaluation.reason)}</p>}
              </Notice>
            ) : (
              <>
                <div className="list-row">
                  <div>
                    <strong>Происхождение отчёта</strong>
                    <small>
                      Снимок: {date(evaluation.generated_at)} · проверено
                      файлов: {metric(evaluation.provenance?.checked_files)}
                    </small>
                  </div>
                  <Badge>{evaluation.provenance?.status || "Не указано"}</Badge>
                </div>
                <p className="safe-data-note">
                  Report SHA256:{" "}
                  {evaluation.provenance?.report_sha256 || "Не указан"}
                  <br />
                  Stability SHA256:{" "}
                  {evaluation.provenance?.stability_sha256 || "Не указан"}
                </p>
                {evaluation.notice && <p>{String(evaluation.notice)}</p>}
              </>
            )}
          </div>
          {measurements && (
            <div className="v-measurement-sections top-gap">
              <div className="linear-section">
                <div className="panel-header">
                  <h2>Стабильность на синтетических профилях</h2>
                  <Badge tone="amber">Human validity не измерена</Badge>
                </div>
                {[
                  [
                    "Совпадение категорий",
                    measurements.retest?.agreement,
                    true,
                  ],
                  [
                    "Профили с пограничной внимательностью",
                    measurements.retest?.attention_agreement,
                    true,
                  ],
                  ["Пары повторных прохождений", measurements.retest?.pairs],
                  ["Формы теста", measurements.retest?.forms],
                  ["Прохождения", measurements.retest?.administrations],
                  [
                    "Отрицательные item-rest",
                    measurements.retest?.negative_item_rest,
                  ],
                  [
                    "Неположительная разделяющая сила",
                    measurements.retest?.nonpositive_separation,
                  ],
                  [
                    "Неопределённые корреляции",
                    measurements.retest?.undefined_correlations,
                  ],
                  [
                    "Немонотонные сравнения",
                    measurements.retest?.nonmonotonic_flags,
                  ],
                ].map(([label, value, percent]) => (
                  <div className="list-row" key={String(label)}>
                    <div>
                      <strong>{String(label)}</strong>
                    </div>
                    <Badge tone="amber">
                      {metric(value, percent === true)}
                    </Badge>
                  </div>
                ))}
                <Notice tone="amber">
                  Общая доля совпадений не скрывает пограничные профили и
                  отрицательные флаги. Это диагностика синтетических методов
                  ответа; качество профессиональных грейдов на людях не
                  измерено.
                </Notice>
                <p className="safe-data-note">
                  Протокол: {measurements.retest?.protocol_id || "Не указан"}.
                  Проверка банка: {metric(measurements.bank?.forms)} форм /{" "}
                  {metric(measurements.bank?.items)} заданий /{" "}
                  {metric(measurements.bank?.families)} семейств; ошибок oracle:{" "}
                  {metric(measurements.bank?.failures)}.
                </p>
              </div>
              <div className="linear-section">
                <div className="panel-header">
                  <h2>Подбор на отложенных синтетических данных</h2>
                  <Badge>Holdout</Badge>
                </div>
                {[
                  ["P@5", measurements.matching_holdout?.precision5, true],
                  [
                    "nDCG@10 · весь путь",
                    measurements.matching_holdout?.ndcg10_end_to_end,
                  ],
                  [
                    "nDCG@10 · среди допущенных",
                    measurements.matching_holdout?.ndcg10_eligible,
                  ],
                  [
                    "Полнота после обязательных фильтров",
                    measurements.matching_holdout?.retrieval_recall,
                    true,
                  ],
                  [
                    "Нарушения обязательных ограничений",
                    measurements.matching_holdout?.gate_violations,
                  ],
                  ["Запросы", measurements.matching_holdout?.queries],
                ].map(([label, value, percent]) => (
                  <div className="list-row" key={String(label)}>
                    <div>
                      <strong>{String(label)}</strong>
                    </div>
                    <Badge>{metric(value, percent === true)}</Badge>
                  </div>
                ))}
                <h3 className="top-gap">Контрольные методы</h3>
                {[
                  ["random_eligible", "Случайный среди допущенных"],
                  ["keyword_all", "Ключевые слова"],
                  ["strong_category_test", "Категория и результат экзамена"],
                  ["full_neutral", "Основная модель без TF-IDF"],
                ].map(([key, label]) => {
                  const baseline =
                    measurements.matching_holdout?.baselines?.[key];
                  return (
                    <div className="list-row" key={key}>
                      <div>
                        <strong>{label}</strong>
                        <small>
                          P@5: {metric(baseline?.precision5, true)} · nDCG@10
                          всего пути: {metric(baseline?.ndcg10_end_to_end)}
                        </small>
                      </div>
                    </div>
                  );
                })}
                <Notice>
                  Метрики среди допущенных не устраняют потери кандидатов при
                  фильтрации. Эти показатели не предсказывают реальный найм;
                  разметка синтетическая.
                </Notice>
              </div>
            </div>
          )}
          <div className="linear-section top-gap">
            <div className="panel-header">
              <h2>Доставка событий</h2>
              <Webhook size={18} className="purple" />
            </div>
            <p>
              В очереди outbox: <strong>{counts.pending_outbox ?? "—"}</strong>.
              Фоновые операции сохраняются отдельно; принятие приглашения и
              разрешение контактов происходят транзакционно.
            </p>
            <Notice>
              Показатели здесь — состояние приложения. Они не являются отчётом о
              качестве найма или заменой измерений на независимом датасете.
            </Notice>
          </div>
        </div>
        <aside className="linear-properties">
          <h2>Свойства стенда</h2>
          <div className="list-row">
            <span>Среда</span>
            <Badge>Локальная</Badge>
          </div>
          <div className="list-row">
            <span>Данные отчёта</span>
            <Badge>Синтетические</Badge>
          </div>
          <div className="list-row">
            <span>Хранилище</span>
            <span>{runtime.database || "Не указано"}</span>
          </div>
          <div className="list-row">
            <span>Снимок</span>
            <Badge tone={measurements ? "green" : "amber"}>
              {measurements ? "Проверен" : "Не подтверждён"}
            </Badge>
          </div>
          <section className="linear-section">
            <h3>Ограничения</h3>
            <div className="list-row">
              <span>Человеческий пилот</span>
              <Badge tone="amber">Не измерен</Badge>
            </div>
            <div className="list-row">
              <span>Реестр ФСП</span>
              <Badge>Демо</Badge>
            </div>
            <p className="safe-data-note">
              Официальный API ФСП недоступен. Код требует настроенного
              изолированного runner.
            </p>
          </section>
          <div className="list-row">
            <span>Outbox</span>
            <strong>{counts.pending_outbox ?? "—"}</strong>
          </div>
        </aside>
      </div>
    </>
  );
}
export function ATS(ctx: WorkspaceContext) {
  const { data, error, loading, reload } = useResource<Dict>(
    "/employer/ats-deliveries",
  );
  return (
    <>
      <PageTitle
        eyebrow="Интеграция команды"
        title="Доставка в ATS"
        description="События вашей компании, полученные локальным демонстрационным приёмником."
        action={
          <Button variant="secondary" onClick={() => void reload()}>
            <RefreshCw size={14} /> Обновить
          </Button>
        }
      />
      <Notice>
        Это локальный ATS-приёмник. Внешняя система найма не подключена.
        Доставка не даёт дополнительных прав к контактам.
      </Notice>
      {loading ? (
        <Loading />
      ) : error !== undefined ? (
        <div className="top-gap">
          <ErrorBox error={error} />
        </div>
      ) : items(data).length ? (
        <div className="linear-record-list v-delivery-list top-gap">
          {items(data).map((d) => (
            <article className="linear-record-row v-delivery-card" key={d.id}>
              <div className="linear-record-content">
                <h3>
                  {d.payload?.type || d.payload?.event_type || "Событие найма"}
                </h3>
                <small>
                  {date(d.created_at)} · {d.destination}
                </small>
                <details className="top-gap">
                  <summary className="link-action">
                    Открыть полезную нагрузку
                  </summary>
                  <pre
                    className="code-input"
                    style={{
                      padding: 15,
                      minHeight: 0,
                      whiteSpace: "pre-wrap",
                    }}
                  >
                    {JSON.stringify(d.payload, null, 2)}
                  </pre>
                </details>
              </div>
              <Badge tone="green">
                <Check size={11} />
                Получено локально
              </Badge>
            </article>
          ))}
        </div>
      ) : (
        <div className="panel top-gap">
          <Empty
            title="Событий пока нет"
            text="После принятия приглашения событие попадёт в outbox. Запущенный worker доставит его локальному приёмнику."
            icon="spark"
          />
        </div>
      )}
    </>
  );
}

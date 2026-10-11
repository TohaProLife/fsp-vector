# Read-only диагностика B4 и проверка перед сдачей

Дата: 2026-10-07. Это отдельный последующий аудит, а не новый заранее зафиксированный эксперимент и не исправленная версия B4. Банк, responders, rubric, floors, grading и historical baseline не изменены. Полный прогон `evaluation.run` здесь намеренно не выполнялся, чтобы не перезаписывать historical artifacts.

## Сохранённое основание

| Frozen artifact | SHA256 |
|---|---|
| [B4 protocol](../../evaluation/ASSESSMENT-STABILITY-PROTOCOL.md) | `d3f67449b7d8c1d4f4218d40e0263f82882f7d12d31613bf113fb7fdad4347d7` |
| [B4 observations](../../data/evaluation/assessment-stability-observations.json) | `aa7c2ac976e07ddc723fcf871677af9edd8a4fde1198870e3a1de7fc72d6b956` |
| [B4 result](../../evaluation/reports/assessment-stability.json) | `52f64d19700bc1e080476f5393f7f2205f697c4d9d719cc74ac7e6ea7d6ad98b` |

Read-only воспроизведение восстановило все 192 формы по сохранённым seed/exposure и проверило public form SHA, answer SHA, score, pass/fail, failed floors и competencies всех 3840 administrations. Все совпали. Хеши трёх frozen artifacts до и после совпали. Это проверка воспроизводимости, а не независимая человеческая валидация oracle или difficulty.

## Почему attention-boundary нестабилен

[`bank.py`](../../services/api/app/engines/bank.py), строки 304–321, выдаёт по три задания на каждую из четырёх тем, из них одно advanced practical для Middle/Senior. [`assessment.py`](../../services/api/app/engines/assessment.py), строки 41 и 220–227, требует минимум 50% по advanced части **каждой** темы. Для бинарного advanced item одна ошибка означает 0% по этой теме и FAIL, даже если общий результат высокий. Для частичного rubric item ошибка критического поля ограничивает результат 40%, также ниже этого floor. Это явная авторская policy, а не найденная арифметическая ошибка. Её не ослабляли ради стабильности.

В [`responders.py`](../../evaluation/responders.py), строки 26–43, attention — фиксированная авторская propensity от 0.70 до 0.95, дополнительно сниженная на 0.15 в одной теме. Digest публичного содержания определяет применение actual flawed method. Это модель пропусков условий, не наблюдаемая вероятность поведения людей.

В 480 disjoint attention A/B pairs ровно 208 решений расходятся:

| Requested grade | Pairs | Разные raw решения |
|---|---:|---:|
| Intern |120|46|
| Junior |120|50|
| Middle |120|55|
| Senior |120|57|

У неуспешной стороны этих 208 пар floor `competency` встречается 130 раз, `advanced_competency` — 104, `overall` — 61, `practice` — 57, `advanced_overall` — 22. Причины пересекаются; их нельзя складывать как число независимых неуспехов. Among discordant pairs имеются FAIL с общим score 91.67, 93.75, 94.44 и 95.0: высокий общий балл не заменяет обязательное практическое evidence.

Воспроизведение не обнаружило расхождения oracle/ответа/назначенного балла, которое объясняло бы 56.67% agreement. Сочетание редких заданий по теме, заданной вариации внимания и обязательных floors даёт конкретный механизм чувствительности. Неизвестно, соответствует ли этот механизм реальным кандидатам; для этого нужны новые независимые данные и human pilot.

## Что означает 49 negative flags

Frozen B4 определяет corrected item-rest correlation против остальных **11 заданий всего теста**, исключая собственные пункты; [`stability.py`](../../evaluation/stability.py), строки 37–49 и 79–85. Сам item не входит в rest. В этой формуле арифметической ошибки не выявлено. Группы отражают смесь неоднородных method profiles и повторов, а не одномерную человеческую способность.

Дополнительная **post hoc описательная диагностика тех же данных** дала:

- Для 48 из 49 negative whole-test families связь с остальными двумя заданиями собственной competency неотрицательна. Единственное оставшееся отрицательное значение: backend/Middle SQL short, `concept.3fae7ce197c4`, «SQL: последний заказ с tie-break», correlation −0.085531. Это повод предметно проверить family; знак не доказывает ошибку условия и не снимает остальных flags.
- Исключение shallow profile делает неотрицательными только 13 из 49 correlations; 36 остаются отрицательными. Объяснение одной только memorization-моделью недостаточно.
- Для upper/lower 27% границы с одинаковым rest выбираются по `profile/repeat`. Это заранее заявленная воспроизводимая tie policy, но итоговая separation может зависеть от состава граничных ties. Среди 47 исторических nonpositive values 6 могли бы стать положительными при другом допустимом выборе равных по rest наблюдений. Всего 27 family groups имеют диапазон допустимых separation, пересекающий ноль. Frozen point estimates и все flags сохранены.

Допустимый диапазон ties получен без изменения score или group size: все значения ниже/выше boundary остаются фиксированными, для оставшихся мест выбираются наименьшие/наибольшие item fractions из одной rest-tie группы; lower и upper disjoint. Это диапазон комбинаторной чувствительности, **не** confidence interval или новый критерий PASS. Для нулевой rest variance исходный null сохранён.

43 non-monotonic grade/profile flags также сохранены. У SQL misconception Junior JOIN shortcut случайно выполняет контракт JOIN, хотя Intern shortcut нарушает фильтрацию aggregate; такой профиль не является шкалой одинаковой измеренной профессиональной способности на разных contracts. Этот пример раскрывает ограниченность responder model, а не подтверждает ordinal calibration банка. Выводы по flagged families требуют отдельных предметных review и независимых наблюдений; изменение профилей под прежний результат запрещено.

## Подтверждённый пробел процесса сдачи

[`exam.tsx`](../../apps/web/src/features/exam.tsx), строки 203–210 и 357–363, показывает количество непустых значений без проверки формата. После восстановления native `[]` считается незаполненным, хотя для JSON-задачи множества это допустимый ответ. Строки `{broken`, `NaN` и неизвестный option ID считаются заполненными.

[`assessment.py` API](../../services/api/app/assessment.py), строки 225–232 и 254–256, проверял общий размер, принадлежность IDs и общий Python type, после чего сразу завершал попытку ordinary grader. Ошибка оформления могла стать окончательным FAIL с cooldown, хотя кандидат ещё мог исправить её до истечения времени. Полные syntactically valid ответы attention responders этот пробел не используют: review **не** обещает улучшить B4 agreement и не проверяет метод решения.

Добавлен отдельный pure helper [`app/assessment_review.py`](../../services/api/app/assessment_review.py). Он не меняет frozen engines или старые формы. Backend/root отдельно интегрируют endpoint/DTO и lifecycle; сам helper не выполняет persisted операции.

## Contract и границы нового helper

`review_submission(public_snapshot, saved_answers, draft_answers=None)` проверяет prospective merge `{**saved_answers, **draft_answers}` и возвращает:

```json
{
  "answered": 4,
  "total": 4,
  "structural_ready": true,
  "issues": [],
  "public_form_sha256": "<SHA256 of public snapshot>",
  "saved_answers_sha256": "<SHA256 or null>",
  "prospective_answers_sha256": "<SHA256 or null>",
  "review_token": "<SHA256 or null>",
  "limitations": ["...public format checks only..."]
}
```

- `answered` означает число present nonempty значений, включая malformed значения. Только отсутствие issues делает `structural_ready=true`; это не правильность, балл, PASS или разрешение присвоить категорию.
- `None` и whitespace — missing. Native/encoded `[]` и `{}` — ответы JSON. Формат shape не читается из oracle. Native/encoded JSON может быть семантически неправильным и всё же ready.
- Number должен быть конечным числом; bool, NaN/Infinity отклоняются. Choice должен указывать известный public option ID. JSON проверяется на синтаксис, duplicate keys, конечность чисел, Unicode и bounded structure. Для SQL проверяются только nonempty string и лимит 12 КБ; запрос не готовится и не выполняется, синтаксис/результат не проверяются.
- Limits: общий canonical body 100 КБ, JSON string/text 16 КБ, JSON tree 1000 nodes/depth 20/key length 256. Issues имеют только `{item_id,kind,detail}`, где `kind` — missing/format/limit. Unknown IDs дают global issue `item_id=null`; пользовательские неизвестные keys/answer values не отражаются в сообщении.
- Public projection использует существующий allowlist; `_oracle`, `private_payload` и future private metadata не возвращаются и не влияют на receipt. Исторические public rubric/policy/task snapshots включены в SHA; они не заменяются сегодняшней policy.
- Fingerprint = SHA256 canonical object `{review_version,public_form_sha256,prospective_answers_sha256}`. Canonicalization сохраняет IDs/types/values и упорядочивает object keys. Snapshot/task/итоговые ответы изменились — fingerprint другой. Сохранение уже просмотренного final набора не делает token устаревшим; saved SHA остаётся диагностикой.
- Это **unkeyed consistency fingerprint, не authorization, не секрет и не grade approval**. API проверяет identity, ownership, consent, срок, status и receipt под row lock. Это не CAS над earlier saved versions: full draft может намеренно заменить сохранённое значение другой вкладки. Не заявляется защита от злонамеренного кандидата, вычислившего digest самостоятельно.
- Uncanonicalizable/oversized final значения имеют null SHA/token и format/limit blocker. Malformed JSON string канонизируется как строка, но format blocker сохраняется. Invalid saved значение можно исправить полностью заменяющим valid draft; saved SHA может остаться null диагностически, final receipt будет valid.
- Сознательная отправка missing ответов требует отдельного explicit подтверждения на API; format/limit issues его не допускают. Helper сам ничего не завершает и не разрешает категорию. API integration и эти правила submit принадлежат backend/root.

Алгоритм grading и bank не менялись, поэтому новый retest protocol/holdout не создавался. Для будущего изменения decision algorithm потребуется отдельно зафиксированный протокол и новый независимый holdout; текущая диагностическая выборка не может стать его независимой валидацией.

## Проверка и ограничения

`PYTHONPATH=services/api;. python -X utf8 -m unittest discover -s services/api/tests -p test_assessment_review.py -q`: 7 meaningful tests PASS. Проверены public-only/no mutation, запрет вызова grader/SQL, valid empty containers/zero, whitespace, foreign option/bool/nonfinite/malformed/duplicate-key JSON, UTF-8/depth/node/key/body limits, cycles, SHA canonicalization/form/value changes/equivalent autosave, unknown ID privacy, исправление malformed saved value и ready-but-FAIL ordinary grading. Это helper verification; authentication/row lock/expiry/receipt submit интеграцию проверяет backend.

Замороженные B4 артефакты и engine/evaluation source hash maps остаются прежними. Human validity, внимание людей, профессиональная шкала и discrimination на людях по-прежнему NOT_MEASURED. Review уменьшает риск необратимой сдачи технически некорректного ответа; уменьшение ошибок рассуждения или рост test-retest agreement не измерены и не заявляются.

## Дополнительный независимый аудит: quality, privacy и SQL family

Это отдельная **post hoc техническая проверка**, проведённая после описанной выше диагностики. Она не является новым B4 protocol, независимым human holdout или калибровкой банка. Независимый reviewer не редактировал проверяемые production файлы; adverse воспроизведения использовали только временные копии артефактов и actual-route fixtures с отдельной in-memory SQLite базой. Основной runtime DB не затрагивался.

### Целостность агрегированного quality report

При первоначальной независимой проверке [`evaluation_summary.py`](../../services/api/app/evaluation_summary.py) и [`seal_evaluation.py`](../../scripts/seal_evaluation.py) воспроизведены два дефекта:

1. Некорректный `latest.generated_at='not-a-date'` после reseal получал `status=ready` и metrics, но нарушал Pydantic `EvaluationSummary` response contract.
2. Удаление `matching.py` из непустой source SHA map позволяло изменённому matcher оставаться незамеченным: summary возвращал `ready/verified`, проверив 32 файла вместо 33. Sealer также принимал этот неполный snapshot.

Root исправил bounded timezone-aware timestamp validation и требование полной SHA map, равной фактическим `engines/*.py`, `evaluation/*.py` и файлам `data/evaluation/`. Sealer теперь проверяет provisional manifest тем же validator до записи, не перезаписывая manifest при отказе.

Независимый повторный прогон `python -X utf8 -m pytest services/api/tests/test_quality_evidence.py -q -p no:cacheprovider`: **16 tests PASS**. Включены malformed/naive/oversized timestamp, omitted changed matching source, sealer refusal/no overwrite, missing/corrupt/source-stale evidence, unsafe path, read bounds и actual quality endpoint/processing restriction. Текущий полный snapshot возвращает `ready`, `checked_files=33`, `human_validity=not_measured`. Проверены ограничения пути через resolve/relative-to, 8 MiB/file, 32 MiB total, finite numeric/count bounds. Integrity SHA подтверждает совпадение локальных артефактов, а не научную валидность или внешнюю рецензию.

Независимая сверка подтвердила неизменность четырёх исторических артефактов: protocol, observations, B4 result и `latest.json`. Последний сохраняет SHA256 `c4047cbd3faccd61c80946102328108c822d72c3d41cac13cae9247505ee815f`; SHA остальных приведены выше. B4/latest не пересчитывались.

### Privacy: сохранение истории и запрет новых действий

Read-only проверены текущие изменения [`common.py`](../../services/api/app/common.py), [`jobs.py`](../../services/api/app/jobs.py), [`hiring.py`](../../services/api/app/hiring.py), [`auth.py`](../../services/api/app/auth.py), [`worker.py`](../../services/api/app/worker.py) и [`test_backend_privacy_round3.py`](../../services/api/tests/test_backend_privacy_round3.py). Новые guards/redaction различают processing withdrawal, company block и отдельный contact-grant revoke; historical status/owner history сохраняются, employer disclosure ограничивается. ATS dispatch проверяет текущие candidate/company rights перед transport.

В проверенной промежуточной версии обнаружены два непокрытых adjacent action:

- Accepted invitation → employer processing withdrawal `200` → candidate `POST /invitations/{id}/messages` всё ещё `201`, новый private context persisted count=1. В message path отсутствовал current company processing guard.
- Candidate company block → employer `PATCH /applications/{id}` с `status=offer` всё ещё `200`, persisted status=offer. В application-status path отсутствовал current candidate processing/company-block guard.

Оба воспроизведения использовали существующие actual-route in-memory fixtures. Root/backend исправили эти guards и добавили отдельные regression tests: запрещённое действие не изменяет историю, status, notification или audit; явный regrant восстанавливает разрешённое взаимодействие.

В финальной проверке дополнительно воспроизведены и переданы backend два дефекта оформления входных данных:

- Native `NaN` в ответе на manual company challenge сохранялся через SQLite, после чего employer history endpoint возвращал `500` при JSON response serialization. Guard теперь отклоняет NaN, Infinity и invalid Unicode до persistence с `422 ANSWER_JSON_INVALID`; ordinary text для human review не интерпретируется как JSON.
- Raw `x-csrf-token=b'\xff'` вызывал `TypeError` в `hmac.compare_digest` и `500` на logout. Обхода авторизации или изменения сессии не было. ASCII guard теперь возвращает `403 CSRF_REJECTED`; тот же действительный токен после отказа выполняет logout `200`, последующий me — `401`.

Финальный read-only audit diff против `7506298` охватил роль/owner scope, current consent/block checks, lock order, ATS cancellation/retry и token/nonfinite transport. Candidate-scoped mutations начинают с Candidate lock; ATS блокирует Candidate → ContactGrant → owner Account. Совместный Candidate lock сериализует потенциально конфликтующие Grant/owner paths; employer consent mutation блокирует owner Account и не запрашивает обратный Candidate lock. Consumer использует отдельную transaction на один Outbox event, сохраняет attempts при transport failure и повторно проверяет права перед dispatch. Payload имеет allowlist идентификаторов, signed transport запрещает redirects и неконфигурированную production delivery. Подтверждённого deadlock, role/owner bypass, раскрытия private context или некорректной retry/cancellation ветки в проверенном diff не обнаружено. Это ограниченный анализ проверенных путей; PostgreSQL race tests и полный release verify выполняет root отдельно.

Независимый прогон `python -X utf8 -m pytest services/api/tests/test_backend_privacy_round3.py services/api/tests/test_assessment_review_api.py -q -p no:cacheprovider`: **32 tests PASS** за 11.82 s. После добавления последнего CSRF guard отдельно выполнен `test_backend_privacy_round3.py::test_raw_non_ascii_csrf_header_is_rejected_without_logout_or_session_change`: **1 test PASS** за 1.37 s. В обоих прогонах только dependency deprecation warning от FastAPI/Starlette TestClient. Проверки использовали isolated SQLite fixtures; утверждение о PostgreSQL concurrency на их основании не делается. Новых privacy features, изменения retention policy, grader, bank, B4 protocol/responders/данных или основного runtime DB в рамках этого независимого аудита не выполнялось.

### Единственная negative within-competency SQL short family

Предметно проверена только `concept.3fae7ce197c4`, backend/Middle, «SQL: последний заказ с tie-break»: [`scenarios.py`](../../services/api/app/engines/scenarios.py), строка 24, и [`author-review-ledger.json`](../../assessment-bank/author-review-ledger.json), строка 47. Условие требует один последний order каждого customer, при равном `created_at` — больший `id`. Ledger и правильный option совпадают.

`ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY created_at DESC,id DESC)` с внешним фильтром `rn=1` выполняет это правило. PostgreSQL описывает нумерацию внутри partition по оконному ORDER BY, неопределённый порядок peers без дополнительного tie-break и фильтрацию результата window function через subquery. Вариант option «и rn=1» — сокращённое описание стратегии, не standalone SQL с запрещённым window expression прямо в WHERE. [Официальный PostgreSQL 18 tutorial](https://www.postgresql.org/docs/current/tutorial-window.html).

Distractors не задают второго правильного решения: `MAX(created_at)` с JOIN только по времени сохраняет оба заказа при tie; `RANK` только по created_at также сохраняет peers; первая строка без ORDER BY не гарантирует больший id. Определение rank/peer groups подтверждено [официальной PostgreSQL 18 документацией window functions](https://www.postgresql.org/docs/current/functions-window.html).

Конкретного противоречия условия/options/ledger не найдено. Банк и ledger не менялись. Отрицательная correlation в фиксированном method mixture сама по себе не доказывает semantic error этого задания; человеческая разделяющая сила остаётся NOT_MEASURED.

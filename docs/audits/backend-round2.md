# Backend audit, round 2

Дата: 7 октября 2026. Область: R01–R31, серверные права, состояния, история, сохранённый контекст, регулярная практика и готовность хранилища. Код конкурентов не читался и не использовался. Основная PostgreSQL БД не сбрасывалась. Внешние письма и сообщения в рамках аудита не отправлялись: SMTP/ATS негативные сценарии используют тестовые адаптеры и изолированные данные.

## Подтверждённые пробелы и исправления

| Пробел | Последствие | Исправление и проверка |
|---|---|---|
| Опрос перезаписывался, audit содержал только факт прохождения | R13: нельзя прочитать предыдущие ответы | `survey.completed` хранит ответы и версию taxonomy; история принадлежит аккаунту. Два опроса сохраняются независимо. Старые события без ответов отмечены `snapshot_available=false`, ответы не выдумываются. |
| Исторические отклики и решения практики выдавали evidence после отзыва обработки | R16: профиль продолжал раскрываться через обходные маршруты | Общая privacy projection выдаёт только недоступный исторический идентификатор. Блокировка компании также применяется к истории. Контакты, evidence, навыки, title и ФСП не выдаются. |
| Уточнение подборки использовало текущую изменённую потребность | R23: невозможно воспроизвести контекст старой подборки | Дочерняя версия ранжируется по `parent.need_snapshot`. Новый самостоятельный подбор использует актуальную потребность. Тест различает оба результата. |
| Истёкшая попытка получала `finished_at` при следующем открытии | Срок повторной попытки мог продлеваться на дни | Время окончания — сохранённый deadline. Проверка открытия через три дня не создаёт новый штрафной интервал. GET блокирует изменяемую попытку; сохранение ответов блокирует кандидата и перечитывает обработку. |
| Readiness проверяла только `SELECT 1` | БД без таблиц или с незавершённой миграцией объявлялась готовой | Проверяются все необходимые таблицы/колонки metadata и Alembic heads. Несовместимость даёт безопасный 503 без URL, пароля и SQL exception. |
| Production режим допускал небезопасные flags/известные demo credentials | Возможен перенос локальных shortcuts на публичный стенд | Startup требует PostgreSQL, миграции, Secure cookies, HTTPS frontend, SMTP, выключенные seed/create-all. Локальный demo требует loopback frontend. Синтетические аккаунты, их существующие сессии и опубликованный demo пароль запрещены вне локального режима. Root-owned OIDC проверяет собственную конфигурацию. |
| Факт просмотра приглашения не сохранялся | R28: у работодателя нет наблюдаемого просмотра | Candidate GET сохраняет `viewed_at` один раз и создаёт одно внутреннее уведомление. Статус `pending` сохраняет совместимость существующей state machine. |
| Короткие задачи были статическим набором без расписания | R30: нет настоящей регулярной практики | Для candidate+ISO week сохраняется собственный объективный вариант из доверенного практического банка, новые входные условия, дата следующей недели, результат и дедлайн повторной попытки. Другой пользователь/работодатель не получает назначенную задачу. |
| Повтор успешной короткой задачи обновлял evidence без нового измерения | Можно искусственно поддерживать «свежесть» | Успешный повтор возвращает прежнюю submission. После ошибки — 24 часа. Категория никогда не меняется. Повтор не меняет evidence и дату. |
| Оценивание не имело прозрачного контекста потребности | Нельзя показать измеренную связь запроса работодателя и практики | Owned blueprint и need practice работают по опубликованной вакансии либо своему доступному приглашению. Snapshot/hash сохраняется. Неизмеренные технологии указаны отдельно; стандартные веса/пороги не меняются скрыто. Результат имеет `NEED_PRACTICE_OBSERVED`, не присваивает `ASSESSMENT_VERIFIED` и глобальную категорию. |
| SSE допуск проверялся только при подключении | Уведомления поступали после logout/revoke до закрытия соединения | Каждый poll перечитывает session, email и processing consent в короткой собственной DB session вне event loop. Отзыв закрывает поток. Составной cursor timestamp+id не пропускает пачку одинаковых timestamps. |
| Принятая переписка продолжалась после отзыва обработки кандидатом | После отзыва можно было создать новое сообщение и уведомление | Message transaction блокирует кандидата, проверяет актуальный processing и перечитывает приглашение под блокировкой. После отзыва — 409 без нового сообщения. |
| Последняя ошибка email оставляла `retry_pending` после terminal outbox failure | UI обещал повтор, который уже не состоится | После пятой неудачи и event, и MailMessage имеют `failed`; delivered_at остаётся null. |

## Контракты для интеграции

Все маршруты ниже имеют prefix `/api/v1`, используют существующие opaque sessions и права/CSRF. Миграция и новые колонки для этих изменений не требуются: дополнительные snapshots и scopes находятся в существующих JSON полях.

- `GET /candidate/survey-history`: `{items:[{id,created_at,taxonomy_version,answers,snapshot_available}],total}`; та же история в `profile.survey_history`.
- `GET /assessments/availability?specialization=backend`: свои `items[{grade,allowed,next_allowed_at,reason,confirmed_grade,policy_version}]`, active attempt и server time. Need practice исключена из политики изменения глобального грейда.
- `GET /employer/needs/{id}/assessment-blueprint`: owned need, точные competencies/priorities, tested/unmeasured skills, snapshot hash и ограничения.
- `POST /assessments/need-start`: ровно одно из `{invitation_id}` / `{vacancy_id}`. Чужой, закрытый или заблокированный источник недоступен. Попытка имеет `scope=employer_need_practice`, `context` и `certifies_global_category=false`; ответы/сдача используют существующие assessment endpoints.
- Need result: `confirmed_grade=null`, `global_confirmed_grade` только отражает прежний глобальный грейд, `category_changed=false`. Evidence не выдаётся другой компании. Practice не открывает контакты. Повтор по тому же контексту — через 24 часа; пересекающиеся активные formal/need попытки запрещены.
- API `category_changed` — фактическое изменение сохранённой категории; `category_change_allowed` и `certifies_global_category` также вычисляются сервером и всегда false для demo/need practice. Старое неоднозначное engine поле `category_change` исключается из новых результатов.
- `GET /challenges/weekly`: `{week_id,opens_at,next_week_at,timezone:'UTC',challenge,submission,completed,retry_at,policy}`. Weekly challenge — обычная safe public task; сдача через `/challenges/{id}/submit`.
- `POST /candidate/consents` также принимает purpose `practice`. `GET/POST` возвращает `effective_practice_notifications`. По умолчанию cadence включена только в явно локальном demo; production требует записанного opt-in. Worker создаёт внутреннее уведомление/outbox, SMTP cadence не используется.
- Invitation добавляет `viewed_at`; перечитывание не создаёт повторного события просмотра.
- SSE может завершиться `event: session-ended`, `data: {"code":"AUTH_REQUIRED"}`; следующий запрос заново проходит обычные права.

## Покрытие требований

| Требования | Подтверждаемое состояние |
|---|---|
| R01–R02 | Одноразовое email подтверждение, verified/processing prerequisites, роли, owner checks, CSRF/Origin и ограничение неудачных входов проверяются сервером. Production отдельно блокирует demo credentials. |
| R03–R04 | Ручной профиль, настоящее Unicode PDF, bounded import с подтверждаемым SELF_DECLARED draft существуют. PDF sandbox относится к отдельному ранее проверенному компоненту; эта итерация не меняет его реализацию. |
| R05–R06, R13 | Сохраняются versioned survey snapshots; declared grade отдельно от confirmed grade. История assessment и survey принадлежит своему аккаунту. |
| R07–R09 | Попытка/форма/ответы/рубрика сохранены; сервер оценивает объективные задания. Engine-agent отдельно проверяет банк, перенос ответов и rubric v2. Человеческая валидность и рыночная калибровка не измерены. |
| R10–R12 | Неуспех сохраняет глобальную категорию. Собственная availability возвращает сроки 90 дней для смены, 7 дней для того же грейда и 24 часа для неудачи. Practice-only результаты не обходят и не расходуют formal cooldown. |
| R14–R15 | Identity-bound demo ФСП и отсутствие ФСП не блокируют основной путь. Официальная интеграция остаётся недоступной без API оператора реестра. |
| R16, R27 | Раздельные processing/publication/FSP/practice permissions, company grants, revoke, block и privacy projections применяются сервером, включая историю и SSE. Need practice не открывает контакты. |
| R17–R18 | Компания и потребность сохраняются; salary/таксономия валидируются. Потребность имеет прозрачную оценочную карту. |
| R19–R22 | Отбор/ранжирование используют подтверждённую категорию и допустимые источники. Декларации резюме не присваивают подтверждение. Engine-owned hard gates, freshness, FSP и benchmark проверяются отдельно. |
| R23 | Базовая и дочерняя подборки сохраняют контекст/фильтры; права перечитываются при каждом чтении. Current need edit не переписывает историю. |
| R24–R26 | Приглашение необязательно связано с вакансией. Условия компании/контакт/положительная зарплата от–до проверены API и БД. |
| R28 | Pending/viewed timestamp/accepted/declined/withdrawn/expired видны сторонам. Принятие/отзыв и повторное принятие проверены PostgreSQL race tests. Переписка прекращается после отзыва обработки. |
| R29 | Публикации вакансий, собственные отклики, employer statuses и company-scoped grants persisted; ownership и отзыв не являются только UI поведением. |
| R30 | Weekly персональная объективная задача, завершение, recurrence, retry policy, дата evidence и внутренний cadence persisted. Многопоточность не создаёт дубли задачи/уведомления. |
| R31 | Durable outbox, retry/terminal/cancelled states и подписанный deployment-configured ATS adapter имеются. Конкретные delivery/security тесты отделены от обещаний полной промышленной надёжности. |

## Выполненные проверки

1. `python -m pytest services/api/tests/test_backend_round2.py services/api/tests/test_domain_api.py -q --tb=short`: **35 passed, 16.73 s**, до завершающих двух regression cases и обновления зависимостей. Новый scope не сломал существующие domain contracts.
2. `RUN_PG_AUDIT=1 python -m pytest services/api/tests/test_postgres_concurrency.py -q --tb=short`: **9 passed, 13.21 s**. Используется новая случайно именованная `vector_backend_audit_*` БД; её удаление ограничено ровно БД, созданной fixture. Основная БД не изменяется. Дополнительно к прежним гонкам проверены 6 weekly GET и 2 scheduler consumers → одна задача/одно уведомление; save answers vs processing withdrawal.
3. После обновления FastAPI **0.142.2**, Starlette **1.7.0**, PyJWT **2.15.1**, pypdf **6.19.0**, multipart **0.0.32**, pytest **9.1.1**: `python -m pytest services/api/tests/test_backend_round2.py -q --tb=short`: **18 passed, 8.68 s**. Единственное предупреждение — deprecation httpx transport в Starlette TestClient; assertion failures отсутствуют.
4. Read-only probe новой реализации на живой PostgreSQL основной БД: транзакция `SET TRANSACTION READ ONLY`, результат `{schema:true,migration:'checked'}`. Пробник не запускает seed/lifespan и не пишет секреты/сырые DB exceptions.
5. После уточнения семантики engine `category_change_allowed` выполнен targeted `test_failure_and_demo_attempt_never_downgrade_or_assign_grade`: **1 passed, 8.02 s**. Demo pass не разрешает смену/сертификацию глобальной категории; FAIL сохраняет прежнюю категорию.

Общий release прогон, browser smoke и проверка обновлённых PDF/OIDC принадлежат root и не подменяются этим targeted аудитом.

## Ограничения и границы утверждений

- Human pilot, переносимость авторских cut scores на рыночные грейды и сопоставимость форм на людях остаются `NOT_MEASURED`. Объективная программная проверка не заменяет эти исследования.
- На текущем Windows нет проверенного Linux isolated programming runner. Без него произвольный пользовательский код не исполняется; доступны ограниченный SQL и декларативные задачи.
- Weekly duration 10 минут — продуктовая оценка, не измеренное время пилота. Recurrence фиксирована по UTC ISO week, что явно возвращается API.
- Старым audit events нельзя восстановить отсутствовавшие ответы. У старых приглашений без snapshot практика использует доступную текущую structured need; новые приглашения фиксируют snapshot при создании. Историческая подборка уже хранит собственный snapshot и не зависит от этого fallback.
- Readiness проверяет наличие обязательных таблиц/колонок и revision, но не доказывает качество backup/restore, полноту индексов, latency или эквивалентность SQL типов после ручного повреждения БД.
- SMTP/ATS остаются at-least-once: сбой после внешнего принятия, но до commit может привести к повтору. Стабильные Message-ID/event ID и idempotent receiver сокращают последствия; exactly-once across transport не заявляется.
- Уже просмотренные человеком контакты нельзя технически удалить из его памяти/локальной копии. Отзыв прекращает новую выдачу в приложении и новые разрешённые доставки.
- Candidate advisory helper engine не выставлен отдельным API в этой итерации. Неизмеренные требования остаются честными gaps, а не заполняются придуманными обещаниями повышения score.
- Production guards предотвращают известные небезопасные конфигурации, но не являются утверждением о завершённом публичном deployment или полном правовом соответствии.

После этих изменений backend domain/API files заморожены для итогового интеграционного запуска root. DB schema migration не потребовалась.

## Завершающий аудит traceability и контракта

При подготовке [матрицы R01–R42](../submission/requirements-matrix.md) подтверждены и исправлены ещё три пробела:

1. `create_match` строил engine projection без company, теряя need practice собственной компании. Теперь company scope сохраняется, а contacts/name/bio удаляются до ранжирования. API A/B regression: свежая объективная практика для A даёт A не более 1.25 дополнительного пункта; B имеет прежнюю freshness и score. Engine дополнительно проверяет company scope независимо от projection.
2. Weekly rotation выбирала только `slot=practice`, пропуская `mutation` competencies. Выбираются оба объективных practical slot; список сначала сортируется по competency, потому что form order shuffled. Новая проверка четырёх последовательных недель охватывает все четыре competencies во всех specializations, при сохранении случайных новых входных данных.
3. Autogenerated success OpenAPI имел пустые object schemas и не показывал opaque cookie boundary. Добавлен `app/contracts.py`: reusable Pydantic core response schemas, явный GenericObject для оставшихся динамических payloads, cookieAuth/CSRF/role/processing metadata, реальные ProblemDetails/media/PDF/SSE/302 descriptions. Используется effective-route traversal нового pinned FastAPI, включая lazy included routers. Runtime73 paths/58 schemas. Contract tests валидируют настоящие persisted ответы и sanitized500/503, а не отдельно выдуманные JSON examples.

В рамках отдельной frontend-owned оптимизации `common.py` получил fresh request-local bulk permission helper; backend интегрировал его после фильтрации eligible и в saved-match read с одним bulk Candidate SELECT. Нет межзапросного кэша. Unknown ID/identity mismatch/другая компания/отзыв внутри Session/commit invalidation остаются fail closed и проверяются dedicated tests.

Завершающая команда:

```powershell
$env:PYTHONPATH='services/api'
.venv/Scripts/python.exe -m pytest services/api/tests/test_contracts.py services/api/tests/test_domain_api.py services/api/tests/test_backend_round2.py services/api/tests/test_projection_performance.py -q --tb=short
```

**56 passed, 18.27 s** после обновления зависимостей: 5 contracts +21 domain +20 round-two +10 bulk projection tests. Один Starlette TestClient transport deprecation warning; assertion failures отсутствуют. DDL/migration не менялись. Новый live latency benchmark, полный mass verify, client export, restart и конечные media/manifest выполняет root. Targeted verification не является утверждением о завершении этих шагов.

Backend source повторно заморожен; matrix/documentation оставляют человеческую валидность, Docker run, завершение упаковки/видео и неполученные runtime метрики явными статусами, без придуманных PASS.

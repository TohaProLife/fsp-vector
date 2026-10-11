# ФСП Вектор — сверка финальной Contra-редакции

Дата: 11 октября 2026. Текущие измеренные media/source результаты и границы закреплены в [release.md](release.md) и [release.json](release.json). Внешняя сдача не выполнена.

## Текущая основа и реализованные изменения

Текущая визуальная основа — один референс Contra Hire, выбранный root по последнему указанию пользователя довести весь сайт. Реализация ФСП Вектор оригинальная. Исторические Attio, Figma C/Linear и другие исследованные направления не являются действующей authority.

В текущих исходниках присутствуют светлая главная, разделённая авторизация, крупная identity паспорта и читаемые карточки специалистов, вакансий и потребностей. Строки свидетельств разделяют содержание, источник, дату, балл и действие; свойства показаны отдельно. Профиль сгруппирован по опыту, условиям и контактам. Экзамен сохраняет реальную позицию, состояние ответа, карту заданий, проверку перед отправкой и сохранённый результат. Пустые данные и недоступная среда не превращаются в успешный результат.

Оригинальная иллюстрация: `apps/web/public/assets/vector-ribbon.png`, 1536×1024, RGBA при чтении изображения. Она используется в коде главной и авторизации. Prata, Golos Text и Inter обслуживаются с локального origin; файлы OFL/лицензий присутствуют в `apps/web/public/fonts/`, происхождение описано в [THIRD_PARTY_NOTICES.md](../../../THIRD_PARTY_NOTICES.md). Код содержит адаптивные правила, focus и reduced motion. Это проверка наличия и структуры реализации, а не измерение всех вычисленных стилей или каждого устройства.

Основа функциональных требований: [01](../../01-case-and-competition.md), [02](../../02-architecture.md), [03](../../03-product-mechanics.md), [04](../../04-data-and-validation.md), [05](../../05-development-plan.md) и [IMPLEMENTATION-CONTRACT](../../IMPLEMENTATION-CONTRACT.md). Реальная интеграция определяется серверным кодом и [OpenAPI](../../api/openapi.json); в экспортированном файле прочитаны 74 paths.

## Измеренные проверки этого этапа

| Проверка | Результат | Граница измерения |
|---|---|---|
| Frontend после структурной переработки | 90/90 PASS; 8094,1496 мс; exit 0; skips/failures 0 | `npm run test:routes`, существующие handlers/helpers/components; не браузерный аудит |
| Frontend после отображаемых названий компетенций | 90/90 PASS; 6350,9892 мс; exit 0; skips/failures 0 | Новое чисто презентационное использование `competencyLabel`; ключи evidence и rubric не менялись |
| API + engines + integration | 268 tests PASS и 324 subtests PASS; 86,94 с; exit 0 | Полный существующий набор без opt-in PostgreSQL модуля; отдельные SQLite-базы в памяти |
| Синтаксический parse обновлённых feature TSX | 4/4 PASS; затем candidate/exam 2/2 PASS после коррекции подписей | TypeScript parse и форматирование только назначенных файлов; не production build/typecheck всего приложения |
| Независимая сверка API-вызовов и event handlers | Действующие mutation handlers сохранены | Нормализация TypeScript AST текущих изменений относительно HEAD; runtime/browser не запускались этим аудитором |

Диагностические журналы сохранены локально: `.local/contra-route-audit-20261011.log`, `.local/contra-route-labels-20261011.log`, `.local/contra-backend-audit-20261011.log`, `.local/contra-domain-diff-audit-20261011.log`. Время последней записи соответственно: 17:29:56 UTC, 17:35:22 UTC, 17:31:16 UTC и 17:32:22 UTC 11 октября. Это readback metadata файлов, а не придуманные времена начала прогонов. `.local` исключён из Git и сдаваемых исходников; команды можно воспроизвести самостоятельно.

Backend-прогон получил одно `StarletteDeprecationWarning`: использование `httpx` с `starlette.testclient` устаревает. Предупреждение зависимости не сопровождалось падением теста. Проверки выполнялись отдельным процессом, основной supervisor не останавливался и продуктовая БД не изменялась. Fixtures создают собственные `sqlite://` engines; OIDC использует подписанный тестовый протокол, процессные проверки подменяют OS lookups/termination и не завершают живые процессы.

14 PostgreSQL concurrency checks **не выполнялись заново** в этом прогоне. Предыдущий [backend-attio.json](backend-attio.json) содержит исторические 282 tests + 324 subtests PASS за 76,28 с, включая эти 14 checks в отдельной временной PostgreSQL audit-БД. Этот исторический факт нельзя выдавать за новое измерение Contra.

Воспроизведение регрессий из корня workspace:

```powershell
Push-Location apps/web
npm run test:routes
Pop-Location

$env:PYTHONPATH = ".;services/api;services/api/tests"
$env:DATABASE_URL = "sqlite://"
$env:AUTO_SEED = "false"
$env:AUTO_CREATE_SCHEMA = "false"
$env:LOCAL_DEMO = "true"
$env:RUN_PG_AUDIT = "0"
.venv/Scripts/python.exe -X utf8 -m pytest services/api/tests tests/integration --ignore=services/api/tests/test_postgres_concurrency.py -q -ra
```

Переменные среды относятся к запущенной тестовой PowerShell-сессии. Эти команды не запускают или останавливают основной supervisor. Отдельный PostgreSQL audit запускается явно через существующий `./scripts/verify.ps1 -Postgres`; его новый PASS здесь не заявляется.

## Совместимость предметных операций

Сверка не обнаружила изменений API/DTO в `apps/web/src/lib` и `services/api/app` за визуальную переработку. Вызовы API и действующие обработчики экзамена, программной практики, практики потребности, компании, подбора, операций, авторизации и workspace сохранились. В профиль добавлены только два reload действия для честного состояния отсутствующих данных; в каталоге вакансий — два сброса локального поиска.

Из старой таблицы откликов удалён дублированный обработчик `PATCH /applications/{id}` внутри недостижимой ветки: AST показывал `employer=true` одновременно с внешним `employer=false`. Действующий employer pipeline сохраняет controlled status, busy gate и `updateApplication` с реальным PATCH/readback. Это не удаление рабочего перехода статуса.

`competencyLabel` применяется только к отображаемому названию; серверные ID, ключи массива компетенций, scope и баллы сохраняются. Категория показана через `specName` и `gradeName` только при существующем серверном `category`. `categoryProvenance`, различение синтетического/реального экзамена, self-declared/registry/practice evidence, readonly account email, `reviewSubmissionAllowed`, просмотренный снимок ответа, `needStartBody`, ownership/consent guards и fail-closed runner не изменены.

## Финальная сверка

Последний frontend после Overview: 90/90 PASS; 12157,8546 мс. Production build/TypeScript PASS. Независимый статический reviewer закрыл шесть замечаний и отдельный Overview copy finding: [вердикт](contra-design-review.md). Видео и PDF прошли собственные свежие проверки. Source install и итоговые ZIP bytes читаются в соответствующих датированных отчётах; предыдущие Attio/C proofs исторические.

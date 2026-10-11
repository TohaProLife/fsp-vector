# ФСП Вектор: итоговая проверка 11 октября 2026

Локальная версия сайта, видео, техническое руководство и комплект исходников готовы. Приложение проверено на сборке C; 282 серверных теста и 324 подслучая, 90 frontend tests, HTTP smoke и 48 наблюдённых desktop/mobile видов прошли. Видео сверено по всем 50 главам, PDF проверен, исходный архив установлен отдельно. Вложенный и внешний ZIP прошли CRC, все исходники и артефакты проверены по SHA256, runtime совпадает с установленным архивом. Известных P0 в проверенном контуре не осталось; это не утверждение о всех состояниях. Git приватный и локальный. Конкурсная ссылка репозитория, доступ жюри, презентация и загрузка ещё не выполнены: ready_local=true, ready_for_submission=false.

Основание: оригинальные `docs/01`–`docs/05`, `IMPLEMENTATION-CONTRACT.md`, ответы экспертов, [матрица R01–R42](../../submission/requirements-matrix.md). Презентация исключена пользователем из этой работы. Git остаётся локальным и приватным, remote не создан; проект не опубликован и на конкурсную платформу не загружен.

## Исправления финального прохода

- Профиль сохраняет разрешённые phone/telegram, не отправляя readonly verified email. Пустая зарплата не становится ложным нулём; сохранение и reload проверены реальным UI, 5 profile-save cases входят в финальные frontend tests.
- Talent/details/refine используют отдельные поколения запросов: старый ответ не подменяет текущие фильтры, снимок потребности или закрытое окно. Новая потребность не уточняет подборку старой need.
- Две owned истории имеют серверную пагинацию с истинным total и сохранёнными snapshots: default30/max100. Чтение истёкшей собственной попытки фиксирует expiry без изменения ответов/категории.
- Отклик требует явного strict boolean contact consent до записи. Повторное действие не восстанавливает отозванный company grant; server projection перечитывает актуальные права.
- PDF и UI различают synthetic, self-declared, formal assessment, demo/real registry, revoked/stale и company-scoped evidence. Практика и ручной review не присваивают глобальный грейд.
- SSE notification и polling fallback обновляют собственные domain resources после успешного authorized read, сохраняя message draft. Практический feedback остаётся после submit; поздние ответы не переносятся на новую задачу.
- Matching v4 учитывает статус/валидность formal и ФСП, отзыв и дублирование достижений; прежние подборки сохраняют algorithm version. Веса 55/20/10/5/5/5 и assessment пороги не подгонялись под отчёт.
- Утверждённый 9 октября C интегрирован: тёмная публичная страница, светлый inset workspace, focus/reduced-motion/мобильное меню; gap-колонка quality адаптирована.

Подробности и промежуточные failures не скрыты: [backend](backend.md), [frontend](frontend.md), [engines](engines.md), [independent](independent.md).

## Измеренные проверки

| Проверка | Факт и область |
|---|---|
| Полный pytest API + engines + integration | `RUN_PG_AUDIT=1`: **282 tests +324 subtests PASS**, 58,05с, 0 failures; 1 Starlette TestClient deprecation warning. JUnit локально: `output/final-2026-10-11/pytest.xml`. |
| Frontend | **90/90 PASS**, последний повтор 2241мс; typecheck и production build PASS. Helpers/handlers/components проверяются с ограниченными transport boundaries; это не все browser states. |
| Работающий стенд | HTTP smoke **6/6 PASS**; native loopback web3000/API8000, локальные PostgreSQL/identity/mail/ATS. |
| OpenAPI | Актуальный экспорт **74 paths**, generated TypeScript и typecheck PASS; contract tests включают history pagination DTO. |
| Браузер | [browser.json](browser.json): **21 desktop1440×1000 +21 mobile390×844**, 0 horizontal overflow/alert. [browser-public.json](browser-public.json): ещё6 views `/`, `/login`, `/register` в двух viewport без overflow/alert. Focus cycle мобильного меню проверен. |
| Восстановление БД | [backup-restore.json](backup-restore.json): **31 таблица/1687 строк**, revision0001, новый isolated restore target; primary DB не изменена, identity DB не включена. |
| Advisory scans | [dependencies.json](dependencies.json): **42 Python packages**, 0 OSV findings; npm audit0 published findings. Контейнеры/ОС/JRE/Keycloak этим scan не охвачены. |
| HTTP benchmark | [http-benchmark.json](http-benchmark.json): **120 authorized reads/concurrency8/45 published synthetic profiles/0errors**; bank p95147,92мс, categories147,26мс, dashboard311,41мс. Не production load capacity. |
| Ресурсы | [resources.json](resources.json): i5-11300H, 15,7GB RAM, 8 logical CPU; selected working sets1190,14MB; warm readiness7,716с. Короткий idle CPU sample2,368с; shared pages могут учитываться повторно, setup/download/build исключены. |
| Source install | [source-archive.json](source-archive.json): **повтор PASS, 2026-10-11T14:54:46Z** после encoder correction. Fresh venv/exact locks/pip check, npm ci/build, SQLite/Alembic и actual isolated API8002/web3002; local font C, same-origin login/CSRF/profile PATCH/readback. Проверенный source commit `eed113be382d8048e67a1ce1164a0f4bf65b8bf5`. |
| Технический PDF | [pdf.json](pdf.json): **passed_unicode_text_bounds_and_sampled_visual_review**,9pages/27586characters, word bounds всех9 без overflow, required Cyrillic/content tokens PASS/no PENDING; визуально просмотрены1/5/9.44583bytes,SHA256 `3c533772648bda98f43efa822a01c05497d1d46a241b4aaa0dcc34736f566dae`. Не полный визуальный просмотр всех9 страниц. |

Source install выполнен на **той же Windows машине** с существующими Python/Node, а не на новой ОС. Portable SQLite не заменяет отдельно выполненные PostgreSQL concurrency и main-stand identity/SMTP/ATS проверки. Основной runtime/БД установочной проверкой не изменён. SHA проверенного runtime ZIP не объявляется SHA окончательного комплекта с новыми documents/media; упаковщик должен проверить равенство runtime/source/data хешей.

## Основной сценарий финального видео

Новый `final-demo-20261011@vector.local` (alias9B2A98, candidate id prefix8659E70C) зарегистрирован и подтвердил одноразовую ссылку actual local SMTP. Профиль и Backend/Intern survey сохранены. Двенадцать UI answers прошли ordinary autosave/review/submit в попытке `c5219e57-f995-4c8b-afe0-545989434eb6`: score100 и Intern сохранены сервером. Publication подтверждена отдельно. Финальный повторный вход после обеих company session switches показал backend:intern,4 formal evidences100 и publication без контактов; employer grant после revoke закрыт. Новый restart этого actor не проверялся; старый `release-20261011@vector.local` имеет отдельный ранее измеренный restart proof. Прямой записи score/category в БД не было.

Подбор по required SQL/API и preferred Python/Git допустил **3** кандидатов: новый actor и ранее прошедшие реальные formal attempts контрольные synthetic actors. Index нового actor —74/100 с объяснением. Приглашение «Backend стажёр · финал ФСП Вектор» принято с адресным grant одной компании; двусторонние сообщения сохранены. После contact revoke actual employer re-read закрыл контакты, не удаляя историю приглашения.

**Дополнительные секции явно показывают другого участника**, `release-20261011@vector.local`, и работодателя: создание/структурирование need, отдельный Middle vacancy apply с честным Intern cover letter, review stage обеих сторон, weekly public-data score100 с сохранённым feedback, fail-closed code runner, signed local ATS receipt и ready quality. Эти результаты не приписываются новому core actor и не повышают его категорию.

Actor/компании синтетические. SQL/data reference answers вычислены из публичных условий; choice использует авторские FACTS/ledger. Это автоматизированный интеграционный контроль серверной рубрики, **не человеческий экзамен, независимая внешняя квалификация или human pilot**.

## Проверенное видео и границы метода

[Video proof](video.json): **passed_decode_duration_fps_and_all_chapter_ui_alignment**. Actual encoded duration **207,92с (3:28)**,2842 source captures,50 chapters,24fps,1440×1110 (UI1440×1000+caption110). Все50 chapter midpoint UI samples совпали с ожидаемыми source frames, максимальная средняя RGB ошибка0,7416. Размер5914606 bytes; SHA256 `da226b9df5b8b33e241c41294648c001e43f1559c70caaa278979e9c29cc9096`. Source segment actors и manifest SHA закреплены в proof.

Видео собрано из actual capture sections с вырезанной preparation;39 reading holds удерживают последний фактический кадр главы. Разрешение нормализовано aspect-preserving letterbox; output24fps не означает native24fps capture. Это edited sampled/resampled запись, не lossless/непрерывная native запись и не доказательство каждого intermediate animation frame. Озвучки нет; русские подписи обозначают synthetic identities, automated reference answers и смену контрольного actor.

Исторический draft потерял начальные кадры manifest и имел drift captions при изменении physical sizes. Этот дефект устранён: core перезаписан, encoder нормализует размеры/timebase, final decode и50 UI alignment checks прошли. Старые duration/SHA не используются как финальные.

## Ограничения доказательств

- Официальный API/реестр ФСП отсутствует: demo identity ownership не считается официальной проверкой Федерации. История ФСП необязательна; категории выдаёт formal assessment.
- Произвольный пользовательский код на Windows/API не исполняется. SQL/data ограничены отдельным read-only bounded контекстом. Docker CLI есть; daemon/Compose/образ-healthchecks и actual Linux/gVisor не проверены запуском.
- Синтетический locked holdout v4: P@5 0,8967, end-to-end nDCG@10 0,7055, eligible nDCG@10 0,9585, retrieval recall0,5889, gate violations0. 236/569 relevant synthetic profiles исключены из-за отсутствующего required evidence. Это не эффективность найма или оптимальность весов.
- Банк186 families; основной oracle прогон2400 forms/28800 items и fresh480/5760 без failures. Полный public reference method проходит100/100; защита от внешнего AI/человека не доказана.
- B4: 3840 synthetic administrations/1920pairs/192forms, agreement86,04%, κ0,7226, attention-boundary56,67%. Сохранены49 negative item-rest,47 nonpositive separation,7undefined,43nonmonotonic flags. Human validity/IRT/экспертный грейд/реальные наймы/LLM attack — NOT_MEASURED.
- OIDC проверен signed RS256/PKCE тестовым протоколом, ATS — signed local adapter; commercial vendor integration и public SMTP deliverability не проверены. Отзыв контактов не удаляет уже выгруженные чужие копии.
- 42 browser views и focus checks не являются WCAG/assistive-technology сертификацией, полным device/OS/browser matrix или доказательством отсутствия всех багов. Advisory scans не являются security certification.

## Локальный комплект и внешняя сдача

`output/release/fsp-vector-submission.zip` содержит исходный ZIP без обфускации, PDF, MP4, manifest и инструкцию. Проверены CRC обоих ZIP, все source/artifact SHA и размеры, совпадение PDF с текущим Markdown, соответствие видео метаданным и равенство runtime проверенной установке. Исходных файлов 276; сгенерированные секреты, БД, конкурентные репозитории и сырые записи исключены. Точный финальный commit и SHA находятся в `output/release/manifest.json`, заключительная проверка — в `output/release/verification.json`. Обновления этих документов не меняют установленный runtime; упаковщик повторно проверяет хеши при каждой сборке.

До фактической конкурсной сдачи команда обеспечивает ссылку репозитория и доступ жюри, добавляет отдельно подготовленную презентацию с обязательными слайдами 7–11 и загружает комплект на платформу до 11 октября 23:59 МСК. Репозиторий не опубликован и проект не отправлен. Эти внешние действия не подменяются локальной готовностью сайта и файлов.

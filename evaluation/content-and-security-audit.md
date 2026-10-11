# Аудит оригинальных domain engines

Авторский технический review 07.10.2026. Это не внешний human panel, эмпирическая calibration или security certification.

## Обнаруженные и исправленные дефекты

- `score=None` в evidence ранее мог приводить к exception/высокой default силе. Теперь неизвестная сила=0, raw declarations и FSP не закрывают must-have.
- Итоговый список skills раньше следовал всей competency taxonomy. Теперь каждый item имеет `evidence_skills`; подтверждается только реально проверенное покрытие, с числом наблюдений и отдельной score/strength. Framework/language stack не сертифицируется этим bounded-data маршрутом.
- Skills canonical case normalization раньше могла терять совпадение `sql`/`SQL`; теперь фиксирован словарь канонических значений без дорогостоящей сборки при каждом профиле.
- Фраза причин подбора раньше сообщала совместимость даже при разрешённом мягком расхождении. Теперь частичная/неизвестная совместимость обозначена.
- Повторы одной записи ФСП могли многократно усиливать сигнал. Повторы event_id/protocol/context now deduplicated; stale/revoked/unverified source даёт 0; общий бонус ≤5; неизвестная team role уменьшает вклад и не подтверждает индивидуальный skill.
- Модель fit теперь использует только допущенные public role/skill projections, без raw CV, email, phone, имени и частных профилей.
- Генератор synthetic latent skills использовал set iteration перед случайными draws. Теперь skill order sorted; SHA256 3000 profiles одинаков в отдельных процессах при PYTHONHASHSEED=1 и2: `5ccbf933375d9cd55106fd247d0eb30a087a0a716e83dbd5e5673b55a114b5f0` (evaluation seed941007, include_latent=true).

## Содержательный Senior review по шести направлениям

| Направление | Проверенный ограниченный кейс | Почему решение следует из условия |
|---|---|---|
| Backend | Потерянный ответ/ledger; write skew; версии | Атомарный ledger запрещает повтор эффекта. PostgreSQL RR не гарантирует общий межстрочный инвариант; Serializable retry/guard serializes decision. Latest-version-wins не применяет старое абсолютное состояние. |
| Frontend | Tenant switch, optimistic rollback, устаревшие callbacks | Company scope входит в cache key; permission rechecked. Rollback одной операции не должен стирать другую. Request/version нужен даже при невозможности физической отмены server effects. |
| QA | Риск privacy и воспроизводимая race | Критичные последствия заданы условием. Синхронные барьеры и DB/grant invariants наблюдают гонку; HTTP200/цвет кнопки их не доказывают. |
| DevOps/SRE | Expand-contract, budgets, downstream amplification | Rolling версии coexist, значит schema compatibility обязательна. Host overhead не равен нулю. Deadline/queue/concurrency constraints исключают unlimited retries. |
| Data | Bootstrap queries, schema drift, reproducible cutoff | Пары внутри query зависимы. Unknown status не означает paid. Версия/cutoff отделяет исправленный отчёт от ранее опубликованного. |
| Security | Grant TOCTOU, key rotation, incident cache | Старый scope check не разрешает будущую выдачу после revoke. Unknown kid/algorithm не доверяются token input. Уже увиденные внешние копии нельзя обещать удалить автоматически. |

Каждый выбор имеет заданные ограничения. Там, где реальный мир допускает альтернативы, oracle выбирает выполнение конкретного контрактного условия, не универсально «лучшую технологию». Правильность semantic choices still author-ledger; independent human review NOT_MEASURED.

## Границы практического и grade вывода

Intern/Junior items бинарные; Middle/Senior сложные JSON cases оцениваются по полям, с ограничением40% при ошибке критического поля. Помимо70/50/60, новые формы требуют advanced average60/75 и advanced каждой competency≥50. Старые попытки используют сохранённую policy. Системные cases и data-only упражнения не доказывают production опыт/реализацию языка. На каждом результате указаны реальные темы, mode и author-initial ограничения. Непройденный новый тест не снимает прежнюю категорию. Employer need practice не присваивает category; синтетические seed cards отдельно помечены fixture.

## SQL и данные

Проверены запреты DELETE/UPDATE/DROP, ATTACH, PRAGMA, load_extension, readfile/writefile, application tables/schema introspection, много statements и неизвестные параметры. Recursive10M и большой cross join interrupted по VM budget; результаты>200 rejected. SQL query<12KB, inputrows≤200, functionallowlist, limit columns/string length. SQL string с `$(` остаётся обычными значениями; никакой shell/exec/eval не вызывается. Авторизация операций применяется SQLite authorizer, не наивным substring blacklist.

JSON ответ проверяется по типам (true не equals numeric1), глубине≤20 и ≤1000nodes. NaN/Infinity не проходят numeric oracle. Unknown item IDs rejected; отсутствующие ответы0. Public DTO whitelist strips `_oracle`, seed, future private metadata, family IDs; feedback не содержит active key.

## Измерения и ограничения

186 content families exercised на2400forms/28800items,100seed на24маршрута; latest report содержит фактические метрики и SHA исходников/данных. 77 domain/parser/metric tests; дополнительно480 новых seed forms/5760items,960 advanced omission cases и240 generic-only shortcuts. Extraction:900/900 template field checks,14/14 adverse skill statements,4/4 role/unknown-field cases, включая exact browser probe; requires_confirmation сохранён. Programmatic correctness ≠ human grade validity. Synthetic1200 ранее виденных пар +1200 locked-seed holdout пар ≠ human gold. CPU TF-IDF defaultdisabled: небольшой in-sample Δ не переносится на holdout. Исторический load sample предыдущей версии: шесть потребностей по3000 профилям суммарно1.330сек на этом Windows host одновременно с другими задачами; это не текущий API p95 или concurrency benchmark.

Финальная сверка API выявила потерю company-owned need practice при company=None projection: backend исправляет projection, engine независимо исключает чужой/missing company scope из C/A даже при полном corpus. A/B negative tests не допускают перенос company observations, global weekly practice остаётся отдельным source. Explicit-label loader поддерживает independent input corpus/labels с immutable SHA, не генерирует relevance и не обещает проверенную human origin. Zero-eligible и IDCG0 queries сохраняются; undefined mean=null. Fictional adverse пример3queries/4pairs имеет human_labelers0.

Round2 critical audit и измеренные ограничения: `docs/audits/engines-round2.md`. Формальный must-have использует только ASSESSMENT_VERIFIED текущего scope; practice/manual review не заменяет экзамен. Слабый required ограничивает C: не более minimum_required_strength+0.25. Объективная актуальная практика по нужному навыку добавляет максимум1.25 пункта A в течение90 дней и не повышает formal C.

Официальный QA B1: FSP v3 допускает каждую valid discipline, base0.8 и optional role context0.2, без изменения category/required gates и F5 cap. QA B4: заранее зафиксированная synthetic same-profile procedure выполнена на192forms/3840administrations; raw agreement0.860417, но attention-boundary лишь0.566667,49negative item-rest flags,7zero variance/null и43non-monotonic comparisons сохранены. [Критическая интерпретация](reports/assessment-stability.md) отделяет observed findings от post hoc multidimensional hypotheses. Это не stability PASS, человеческая калибровка или IRT.

Live browser regression: начальный Backend stack `Python, SQL, REST API` отвергался из-за raw-string сравнения. Теперь canonical aliases применяются перед валидацией; requested values сохраняются отдельно от normalized contexts и actual evidence. Catalog публикует atomic allowed_contexts, default_contexts и scope-filtered context_aliases. Все дескрипторы, их атомарные части и defaults шести направлений проверены во всех четырёх грейдах; неподдерживаемый Java по-прежнему rejected.

Live matching regression: offered work_format/employment=`any` раньше ошибочно сравнивался с concrete preference как конфликт. Wildcard теперь симметричен у обеих сторон (`any`/`любой`), включая strict flags. Проверены remote/office/hybrid, full_time/part_time/contract, обратное направление и сохранение strict concrete запретов. Полное отсутствие preferences сохраняет нейтральное .5 без hard gate.

Дальнейшая независимая проверка: человеческий review/пилот, matched forms, реальные hiring labels, LLM regime, external isolated code runner. До этого результаты не называются «эмпирически откалиброванными».

# Финальная проверка backend — 11 октября 2026

Проверены требования `docs/01`–`docs/05`, `IMPLEMENTATION-CONTRACT.md`, 17 ответов экспертов и матрица сдачи. Это аудит backend и его интеграционных границ; браузер, дизайн, запись видео и окончательный комплект проверяет root отдельно. Код конкурентов не использовался, основная БД не сбрасывалась, публикация исходников не выполнялась.

## Исправленные дефекты

1. **Согласие при самостоятельном отклике.** Раньше отсутствие `consent_contacts` означало `True`; API мог создать отклик и открыть контакты компании без переданного согласия. Теперь значение по умолчанию `False`, принимается только JSON boolean. Пустой запрос и `False` отклоняются до любой записи; строка, число и null также отклоняются. Явное `True` сохраняет реальный отклик и разрешение только целевой компании. UI уже передаёт boolean после подтверждения.
2. **История истекших экзаменов.** Раньше история показывала `in_progress`, пока кандидат не открывал конкретную попытку. Профиль, паспорт, история и dashboard теперь условно переводят принадлежащие кандидату истекшие попытки в `expired`, сохраняя исходный `expires_at` как `finished_at`. Ответы, результаты и ранее подтверждённый грейд не меняются. Чужие попытки не затрагиваются; повторный просмотр не начинает заново cooldown.
3. **Происхождение свидетельств в PDF.** Экспорт раньше подписывал любой evidence как «Подтверждение» с техническим source, включая синтетические записи. Теперь PDF различает синтетический пример, обычный экзамен, demo, отзыв/устаревание, наблюдение практики и субъективную оценку компании. Практика явно не присваивает глобальный грейд, синтетическая категория и demo ФСП маркируются. PDF остаётся доступным только владельцу, с `no-store` и Unicode-шрифтом.
4. **Доступ к старой истории (R13).** Отдельные endpoints экзаменов/опросов раньше молча обрезали историю до 30/100 записей. Теперь они принимают `page` (от 1, default 1) и `page_size` (1–100, default 30), возвращают `{items,total,page,page_size}` с настоящим количеством собственных записей. Сортировка timestamp + id стабильна; старые snapshots и taxonomy versions сохраняются. В профиле остаются компактные preview. UI пагинации внедряет frontend отдельно. Неограниченного чтения всей базы нет.

Изменены `services/api/app/jobs.py`, `services/api/app/candidate.py`, `services/api/app/contracts.py`; добавлены 20 фактических API/PDF-регрессий в `services/api/tests/test_final_backend_release.py`. Пагинация имеет reusable typed OpenAPI DTO. Схема БД и сохранённые оценки не переписывались. Экспорт OpenAPI должен отражать новый default `consent_contacts: false` и две страницы истории.

## Проверенные механики

- **R01–R06, R13–R17:** email verification, server role/ownership checks, CSRF/Origin, согласия и отзыв, ручной профиль/PDF import, PDF export, история survey, declared/confirmed distinction, владение demo ФСП ID, полноценное состояние без ФСП, собственный профиль компании.
- **R07–R12, R21:** настоящая попытка/ответы/review/submit, whitelist публичных заданий без oracle, server grading, immutable submission receipt, deadline/cooldown, сохранение предыдущего грейда при FAIL, отсутствие глобального грейда у demo и company practice. Чистые engines и эксперименты отдельно проверяет release_engines.
- **R18–R28:** persisted need, общий банк/категории, приватный input matching без ФИО/bio/contacts, saved context/refine, приглашение без публичной вакансии, зарплатные API/DB ограничения, просмотр/принятие/отклонение/отзыв, scoped grant, ограничение компании и прекращение последующей выдачи контактов.
- **R29–R31:** опубликованные вакансии, отклики/статусы, недельная практика и opt-in уведомления, объективное bounded grading, отдельное manual company review, подписанный ATS receiver/outbox, проверка прав непосредственно перед транспортом и повторная доставка без дублей.
- **R34–R35:** полный OpenAPI/DTO/errors/security, реальные SQLAlchemy transactions и PostgreSQL concurrency. Изолированный PostgreSQL audit создаёт уникальную `vector_backend_audit_*` БД и удаляет только её.

## Измеренные прогоны

```powershell
$env:PYTHONPATH='services/api;.'
$env:RUN_PG_AUDIT='1'
.venv/Scripts/python.exe -m pytest services/api/tests tests/integration --ignore=services/api/tests/engines -q --tb=short
```

Первый baseline: **176 passed + 16 subtests, 64.96 s**. После первых восьми регрессий: **180 passed + 16 subtests, 4 failed, 67.14 s**; четыре failures относятся к `test_quality_evidence.py`, так как engine/evaluation artifacts изменялись параллельно и прежний seal уже не соответствовал новым файлам. Такие метрики API корректно скрывает как `integrity_mismatch`, а не представляет как действующие. Этот промежуточный прогон не объявляется успешным релизом.

Окончательный targeted-прогон после strict boolean: **20 passed, 10.96 s** — 11 новых release-регрессий и 9 PDF parser tests. PDF проверен настоящим экспортом и извлечением текста `pypdf`, включая Cyrillic/provenance/ownership/no-store. `git diff --check` для изменённых файлов прошёл.

После engine freeze и reseal: **187 passed + 16 subtests, 53.51 s, 0 failures.** Включены все non-engine backend tests, `tests/integration` и настоящий изолированный PostgreSQL concurrency audit. `quality/summary` вернулся в `ready`; provenance verified, проверено 33 source/data/report файла. Сохранены adverse retest flags (49 negative item-rest, 47 nonpositive separation, 7 undefined, 43 nonmonotonic), agreement 0.860417 и attention agreement 0.566667. Текущий holdout: precision@5 0.8967, end-to-end nDCG@10 0.7055, eligible nDCG@10 0.9585, retrieval recall 0.5889, gate violations 0. Эти синтетические показатели не являются измерением реального найма.

После пагинации targeted **25 passed, 7.52 s**: 20 release-регрессий и 5 contracts. Две собственные истории по 36 записей действительно читаются на двух страницах без чужих записей; отдельные проверки отклоняют отрицательные/нулевые/слишком большие параметры. Старые результаты в тесте создаются только в изолированной fixture БД из серверного FAIL-ответа, с `demo: true`; ни одного фиктивного PASS или изменения основной БД нет.

**Окончательный полный backend + integration + PostgreSQL после пагинации: 196 passed + 16 subtests, 50.50 s, 0 failures.** После упрощения написания assertion повторно проверена pagination-регрессия: **1 passed, 1.68 s**. Изменённые API/contract/test/audit файлы прошли `git diff --check`. Теперь backend source заморожен; экспорт OpenAPI/клиента и production restart выполняет root.

Во всех перечисленных pytest-прогонах одно предупреждение Starlette об устаревающем httpx TestClient transport; оно не является падением assertions.

## Пределы проверки

- ФСП API организатора не предоставлен; проверено владение ID в явном демонстрационном реестре, не реальная синхронизация.
- Произвольный пользовательский код на Windows/API не исполняется. Граница judge, подписи, replay и конфигурация sandbox проверены тестами; запуск реального Linux/gVisor здесь не выполнялся. Безопасные SQL/data задачи проверяются отдельно от него.
- OIDC проверен через настоящий подписанный тестовый протокол RS256/PKCE и негативные состояния. Это не нагрузочный тест реального identity provider.
- ATS является демонстрационным подписанным адаптером. Commercial vendor integration, удаление уже выгруженных чужих копий и distributed exactly-once не заявляются.
- Human validity, proctoring и предотвращение внешней помощи не измерены; авторская rubric и synthetic evaluation сохраняют эти ограничения.
- Docker/VPS и полный browser/device matrix не проверяются этим backend-прогоном. Новая миграция не требовалась.

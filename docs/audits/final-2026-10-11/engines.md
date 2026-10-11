# Финальный аудит assessment и matching — 11 октября 2026

Проверены исходные требования `docs/01`–`docs/05`, implementation contract, requirements matrix и 17 ответов экспертов. Аудит относится к оригинальным чистым domain engines, локальным синтетическим данным и offline evaluation. Проверка работающего браузера, полного API и deployment относится к отдельным root/backend отчётам. Проект не публиковался; данные действующей БД не сбрасывались и не переписывались.

## Исправленные дефекты

1. Ранжирование принимало неизвестный статус evidence, потому что исключало только несколько негативных значений. Теперь формальное evidence и ФСП принимают только `active`/`verified`, практика дополнительно принимает настоящий серверный `observed`. Trim/case нормализуются; неизвестные, пустые, pending и revoked состояния не закрывают обязательный навык и не добавляют актуальность. Отсутствующее поле status у старых доверенных записей сохраняет active-совместимость.
2. Active-дубликат ФСП перед revoked-дубликатом давал бонус; обратный порядок не давал. Теперь неблагополучная текущая запись одного event исключает весь event независимо от порядка; повторы не умножают бонус. Nested источник должен совпадать с подтверждённым источником registry snapshot. Будущая/отсутствующая/некорректная дата, boolean или дробное место/число участников не дают бонус. Malformed records пропускаются без аварии подбора. Общий потолок 5 пунктов и равноценная спортивная база 0,8 сохранены.
3. Причины fixture-подбора называли синтетическую категорию/навыки подтверждёнными экзаменом. Теперь category/evidence причины прямо называют синтетические примеры и содержат `source_kind`/`source_kinds`; проверка делается по каждой записи, чтобы последующий действительный экзамен не наследовал demo-статус старой оболочки профиля. Demo или company-practice evidence, ошибочно помеченное `ASSESSMENT_VERIFIED`, не закрывает formal must-have.
4. Unpaired Unicode surrogate в SQL/JSON ответе мог прерывать оценку всей попытки. Теперь такой ответ отклоняется; остальные допустимые ответы оцениваются обычной сохранённой рубрикой. Пользовательский Python/JavaScript/shell не запускается.

Новая версия подбора: `vector-match-v4-55-20-10-5-5-5-fsp-validity-formal-company-semantic-neutral`, **75 символов**, optional TF-IDF версия тоже укладывается в 80. Веса, assessment cutoffs, модель ответов и locked seeds под результаты не менялись. Старые сохранённые подборки сохраняют свой algorithm version; новые подборки используют v4.

## Соответствие ключевым требованиям

| Требование / ответ эксперта | Результат проверки |
|---|---|
| R05–R07, B5/B12/B16: специализация × выбранный грейд и server grade | 6 направлений × 4 грейда, 12 заданий на каждой форме, четыре competency × три наблюдения. Только реально измеренные `evidence_skills`; Python/React/полный стек не выводятся из концептуальной проверки. |
| R08–R09, B4/B9/B13: вариативность, сопоставимость, test-retest | Общий сохранённый blueprint/rubric; параметры и least-exposed compatible scenario. Воспроизведены correctness, literal-answer transfer, locked fresh-seed cases и отдельный test-retest. Ни антисписывание, ни human эквивалентность не объявлены доказанными. |
| R10–R12: предыдущая категория и добровольный retest | Engine cooldown/grade tests проверяют 90 дней для смены после PASS, 7 дней same-grade после PASS, 24 часа после FAIL, границы времени и отсутствие глобального эффекта demo/company practice. Реальное сохранение категории/ownership проверяет API suite. |
| R14–R15/B1: ФСП и отсутствие истории | Identity demo-link привязан к email и proof, не свободному ID/ФИО. Источники demo/registry раздельны. FSP отсутствует → 0 положительного бонуса и полный допуск при других выполненных условиях. FSP не обходит category/must-have/privacy gates. |
| R19–R23/B11: подбор, доказательства и объяснение | Непроверенный declared stack не закрывает formal requirements. Weakest required ограничивает coverage; практика ограничена 0,6 strength и 1,25 пункта freshness, company practice доступна только своей компании. Вывод не содержит контактов, имени или bio; дополнительные API права проверяются backend. |
| R30/B2: объективная короткая практика | Safe bounded SQL/declarative grader, отдельный observed source. Регулярность/ownership/notifications/retry реализует persisted backend, сохранённый integration тест подтверждает фактический freshness effect именно для owner company. |
| B7/B15: данные и необязательное ML | CPU-only original synthetic fixtures; inference не получает latent labels. TF-IDF optional и выключен по умолчанию. Arbitrary-language extraction/human relevance не объявлены измеренными. |

## Запуски и измеренные результаты

Baseline: `pytest services/api/tests/engines -q --tb=short` — **77 tests + 274 subtests PASS, 2,28 с**.

После исправлений: `pytest services/api/tests/engines services/api/tests/test_backend_round2.py -q --tb=short` — **117 tests + 308 subtests PASS, 8,68 с** (86 engine tests и 31 существующий integration test). Одно предупреждение Starlette/httpx transport deprecation; assertions прошли. Этот targeted прогон не заменяет полный PostgreSQL release suite.

Fresh `python -m evaluation.run --seeds 100` завершился exit 0. Итог `evaluation/reports/latest.json`: `generated_at=2026-10-11T13:41:36.223297+00:00`, SHA256 `7cd79827416f53e11b1dfc8b1636bb6b3d32276fefa4fd6b844a60b9f10f95ca`. Независимое чтение SHA всех записанных engine/evaluation/data файлов обнаружило **0 несовпадений**. Seal snapshot выполняет root после завершения генерации, до quality/API acceptance checks.

- Correctness: **2400 форм, 28 800 проверок, все 186 семейств, 0 failures**; 19 200 public-data solver checks, 1200 независимых Python SQL-группировок и 9600 author-ledger структурных проверок choice. Ledger не является независимой экспертной оценкой.
- Fresh-seed adversarial: **480 дополнительных форм / 5760 заданий**, 960 missing-advanced-topic проверок и 240 generic-only shortcut проверок, **0 failures**. 14 adverse extraction и 4 role cases прошли.
- Narrow leakage simulation: literal prior answers mean score 22,834, PASS 0/100; перенос choice labels mean 40,916, PASS 0/100. Полный публичный метод даёт **100/100 PASS**. Это сохраняет честную границу: знакомство с методом/банком и внешний помощник не исключены.
- Extraction: **900/900** checks на 150 ограниченных авторских шаблонах; 0 negation-as-required и 0 wrong offsets. Результат остаётся подтверждаемым человеком draft.

| Synthetic split | P@5 full neutral | nDCG@10 end-to-end | nDCG@10 eligible | Retrieval recall | Gate violations |
|---|---:|---:|---:|---:|---:|
| 60 queries × 20 pairs, ранее известный seed | 0,9300 | 0,7284 | 0,9671 | 0,5971 | 0 |
| Locked-seed holdout, ещё 60 × 20 | 0,8967 | 0,7055 | 0,9585 | 0,5889 | 0 |

Потеря latent-qualified профилей с отсутствующим observed required evidence не скрыта: 231/570 relevant pairs в первом split и 236/569 в holdout исключены этим gate. Это tradeoff доказательств и recall, а не гарантия идеального поиска. На holdout TF-IDF Δ nDCG=-0,0009; оснований включать его по умолчанию не появилось. Bootstrap intervals в JSON относятся к синтетическим queries.

QA B4: **3840 administrations, 46 080 ответов, 1920 A/B пар**; raw category agreement **86,04%**, pooled κ **0,722592**, attention-boundary agreement **56,67%**. Сохранены **49 negative item-rest**, **47 nonpositive upper/lower**, **7 undefined variance** и **43 non-monotonic grade/profile** флага. Pooled результат не заменяет per-route и не доказывает human calibration. Пороги/ответная модель не подстраивались.

## Границы готовности

Автоматическая корректность оракулов, политика grade/evidence/FSP и ограниченные synthetic experiments проверены. Human pilot, human form equivalence, empirical IRT, реальные hiring outcomes, LLM attack experiment и фактический Linux/gVisor запуск **NOT_MEASURED**. Официальный ФСП registry API отсутствует; доступна честно помеченная demo identity. Формальный веб-путь и практики по синтетическим данным доступны без GPU, cloud LLM или изолированного code runner; произвольный code runner fail-closed.

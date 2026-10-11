# Отдельный корпус и явная независимая разметка

```powershell
$env:PYTHONPATH='services/api;.'
.venv/Scripts/python.exe -m evaluation.external --dataset data/evaluation/external-example.json --as-of 2026-10-07T09:00:00Z --output evaluation/reports/external-example.json
```

`external-example.json` — заранее заданные вымышленные adverse cases с human_labelers=0. Пример проверяет сохранение пустой выдачи, IDCG=0 и фиксированный denominator P@5. Он не называется human gold или внешним пилотом. Внешний файл загружается непосредственно; labels не вычисляются из synthetic latent generator или engine scores.

Формат `schema_version=vector-explicit-relevance-v1`:

- `origin`: `external_human`, `external_programmatic` или `team_authored_explicit`. `human_labelers` — явное число; только external_human допускает положительное число, остальные требуют0. Происхождение/число остаются предоставленной декларацией: `origin_independently_verified=false`, `human_pilot_claimed=false`.
- `needs`: список с уникальными opaque `id`, specialization, grade, required_skills и skills. Разрешены структурированные условия/зарплата и company_id; свободный текст с идентифицирующими данными не нужен.
- `candidates`: анонимные observed profiles с уникальными opaque `id`, specialization, confirmed_grade (или null), published. Допустимы реальные наблюдения score/evidence/preferences/assessment_at и bounded FSP metadata. Name/email/contacts/CV, `_latent`, labels и неизвестные поля отклоняются. Loader проверяет структуру, не подлинность доказательств предоставленного корпуса.
- `queries`: `{need_id, candidate_ids:[...]}`. Один query каждого need; candidate IDs уникальны и существуют в corpus. Пустой candidate_ids допускается.
- `labels`: `{need_id,candidate_id,relevance}` для **ровно всех** пар queries. Relevance — целое0..3; bool недопустим. Смысл ordinal labels задаётся вашей процедурой; binary precision/recall считают relevant≥2. Missing/unknown/duplicate пары отклоняются.
- Необязательные `corpus_origin` и `label_metadata` с procedure/adjudication/blinded_to_scores/collected_at описывают процедуру. В независимом исследовании нужно реально ослепить разметчиков к scores, сохранить disagreement/adjudication и документировать выборку. Само наличие этих полей не доказывает выполнение процедуры.

Вход ограничен20MiB,500 queries,200 candidates/query,20000 пар,5000 profiles. JSON duplicate keys, nonfinite numeric constants, неверные типы/категории и неполные labels fail closed. Неизвестные поля не игнорируются молча. `input_sha256` относится к точным байтам прочитанного snapshot, labels/corpus SHA — к каноническому содержимому. Изменение loaded labels/corpus после hashing отклоняется.

Labels/metadata не передаются scorer. Need company scope соблюдается даже при полном corpus. Baselines: actual full engine, category/test-only порядок внутри того же eligible pool, random eligible, keyword eligible. Production gates не ослабляются.

Все queries сохраняются независимо от числа eligible/positive candidates. P@5 всегда делится на5. При пустой выдаче и положительном IDCG end-to-end nDCG=0. При IDCG=0 nDCG=null; recall без relevant=null. Aggregates публикуют mean по определённым значениям, defined/undefined/retained counts; полностью неопределённый mean остаётсяnull и не вызывает exception. Отдельно выдаются zero-eligible counts, причины потерь relevant и gate violations.

`--as-of` фиксирует время для воспроизводимого freshness. Оригинальный файл не изменяется и не публикуется. Дополнительный report требует явного `--output`; вывод не содержит сырые profile/contact данные.

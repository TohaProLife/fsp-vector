# Воспроизводимая оценка

Команды из корня проекта:

```powershell
$env:PYTHONPATH='services/api;.'
python -m unittest discover -s services/api/tests/engines -v
python -m evaluation.generate_data --population 3000
python -m evaluation.run --seeds 100
```

Итог `reports/latest.json` содержит окружение, измеренные числа, ограничения и bootstrap интервалы по queries. `latest.md` — читаемое изложение.

Программа отдельно проверяет:

1. Все 24 track×grade маршрута ×100 seeds. Reference data solvers читают публичные условия/данные; SQL oracle сверяется отдельной Python группировкой и реальным ограниченным SELECT. Choice ledger проверки структурные/авторские, не human panel.
2. Прямой перенос предыдущих submitted answers, A/B чередование, перенос текста правильного option, полный известный публичный метод. SQL submitted answer является запросом/методом, а не фиксированным табличным результатом — соответствующая часть переноса отражает перенос старого решения. Результат полного solver служит явной границей антиутечечного обещания.
3. 3000 профилей, 60 queries ×20 пар с заранее заданной latent rubric. Random, keywords, confirmed category+test, полный нейтральный и CPU TF-IDF режимы. P@5 знаменатель всегда 5, отсутствующие позиции нулевые; nDCG отдельно end-to-end и eligible; IDCG=0 считается и сообщается; retrieval recall учитывает потерю latent-fit людей без observed evidence.
4. Извлечение 900 полей в 150 team-authored шаблонах, отрицания и точность source offsets.
5. Locked-seed matching holdout ещё60×20 пар, component/gate ablations и причины потери relevant. Дополнительные480 fresh-seed assessment forms и adverse cases. Это новые synthetic seeds, не human holdout.
6. Отдельный anonymous corpus с **явными labels** через `python -m evaluation.external --dataset ... --as-of ...`. Input/corpus/labels SHA, duplicate/missing/unknown ID rejection, zero-eligible/zero-IDCG retention. См. [EXTERNAL-LABELS.md](EXTERNAL-LABELS.md). Прилагаемый пример вымышленный, human_labelers=0; внешняя human metadata не становится автоматически подтверждённым пилотом.
7. Официальный QA B4: [заранее зафиксированный protocol](ASSESSMENT-STABILITY-PROTOCOL.md), [actual public-method responders](responders.py), [test-retest/item discrimination и критическая интерпретация](reports/assessment-stability.md) / [JSON](reports/assessment-stability.json). Seed2026100704; одинаковые профили с неоднородностью по competency получают восемь независимых форм. Raw category/UNCONFIRMED agreement/κ, score differences и item-rest/upper-lower без собственного задания в rest. Undefined variance/null и диагностические non-monotonic flags сохраняются; synthetic separation не называется human calibration. [Выводы по всем17 официальным QA](EXPERT-QA-ENGINE-AUDIT.md).

Пороги 70/50/60 и advanced60/75 с каждой темой≥50 — author_initial. Человеческий пилот, human gold, IRT calibration, LLM атаки, время человека и фактический найм **NOT_MEASURED**. Мы не подменяем их synthetic результатами. Материал с latent/explicit labels никогда не загружается в inference API. Domain/parser/metric tests проверяют корректность, privacy/source/company scope и отрицательные случаи; число тестов не является оценкой профессиональной валидности. Извлечение проверено на 150 ограниченных шаблонах, 14 adverse skill statements и четырёх role/unknown-field cases; exact measured concept phrases не расширяются до непроверенных технологий, человек подтверждает draft.

CPU TF-IDF optional; настоящий hash корпуса/IDF и рассчитанная cosine similarity доступны в engine output. Модель вычисляет lexical similarity RU/EN со словарём и char ngrams; глубокая семантика не заявляется. Default disabled с общей нейтральной константой S=.5, потому что небольшой synthetic ablation effect не обосновывает включение. Веса остаются фиксированными для всей версии, без индивидуальной перенормировки при пропусках.

Официальный QA B1: FSP v3 даёт всем valid disciplines равную sporting base0.8 и до0.2 за explicit role relevance; mismatch scopes больше не обнуляет спортивный сигнал. Placement/freshness/team provenance, dedup, общий потолок5 и formal category/required gates сохранены. Коэффициенты видны в breakdown/reasons;0.8/0.2 остаётся прозрачной авторской policy, не эмпирически оптимальным весом.

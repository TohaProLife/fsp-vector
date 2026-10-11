# Оригинальные синтетические данные

`demo-seed.json`: 48 подробных профилей, 150 потребностей, 500 demo identity records и шесть объективных коротких практик. `synthetic-candidates-v1.json`: 3000 профилей. `synthetic-needs-v1.json`: 150 потребностей. Данные детерминированы по seed, hash каждого файла находится в `dataset-manifest.json`.

Все имена, контакты, компании и достижения вымышлены. Подтверждения заранее заполненных карточек — **SYNTHETIC_SEED** fixtures, а не результаты реально пройденных людьми тестов. Они явно имеют `is_demo`, `origin`, `calibration_status=synthetic_fixture`. При серверном импорте также создаётся `fixture=true`. Настоящий результат локального пользователя может появиться только после его серверной сдачи.

`candidate@vector.local` начинает без confirmed grade/evidence и без публикации. ФСП привязывается только к его собственной demo identity: `FSP-DEMO-001` / `VECTOR-2026`. Произвольный ID или чужой аккаунт запрещены. Источник — FSP_DEMO_CONFIRMED, не реальный реестр.

`data/evaluation/matching-benchmark.json` и `matching-labels.csv`: 60 потребностей ×20 пар, программная synthetic latent rubric с human labelers=0. Подбор получает только observed fields, не `_latent` или labels. Рубрика не вызывает scorer и не использует его веса/ФСП, однако данные и модель имеют общих авторов — это ограниченная симуляция, не независимая человеческая разметка рынка.

`matching-holdout-benchmark.json` / `matching-holdout-labels.csv`: ещё60×20 пар с заранее зафиксированным новым seed2026101107. Общие искусственный генератор и авторы остаются ограничением; пороги под holdout не подгонялись. `round2-cases.json` сохраняет adverse extraction cases, три карты need→blueprint, новый диапазон assessment seeds400003–400022 и ожидаемые инварианты formal must-have/слабого required/ограниченной практики. Источники human/IRT/LLM не имитируются.

`external-example.json`: anonymous fictional corpus с отдельными явными labels;3queries/4pairs, включая private relevant candidate и IDCG0. Human labelers=0. Это технический adverse пример для `evaluation.external`, не external human benchmark. Внешний корпус/разметка при наличии загружаются непосредственно с immutable SHA и явно заявленной provenance; metadata сама по себе не подтверждает проведённый human pilot.

`data/evaluation/extraction-cases.json`: 150 ограниченных синтетических шаблонов с явными обязательными, предпочтительными и исключёнными требованиями. Высокая точность на них не переносится автоматически на произвольные реальные вакансии.

Генерация не меняет БД и не публикует данные: `python -m evaluation.generate_data --population 3000`. Backend использует тот же `app.engines.seed.demo_seed()` и импортирует fixtures только при явном LOCAL_DEMO. Повторный импорт идемпотентен, не перезаписывает пользовательскую работу.

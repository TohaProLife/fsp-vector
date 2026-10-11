# Synthetic test-retest и разделяющая сила: измеренный результат

Официальный QA B4 допускает synthetic процедуру. [Протокол](../ASSESSMENT-STABILITY-PROTOCOL.md) и seed2026100704 зафиксированы до прогона: SHA256 `d3f67449b7d8c1d4f4218d40e0263f82882f7d12d31613bf113fb7fdad4347d7`. Профили, ответы, рубрика и формулы после результатов не менялись. Ниже измерения и отдельно обозначенная последующая интерпретация; результату не присваивается ярлык «валидность PASS».

192 различные category forms,120 фиксированных specialization-specific profiles,3840 profile-attempt administrations,46080 item responses. Каждый из480 route-profiles получает8форм;1920 disjoint A/B comparisons. Responders читают public conditions и применяют правильные либо заранее заданные ошибочные методы. Балл/grade/UNCONFIRMED возвращает обычный grade_form, прежняя сохранённая категория не маскирует новую неудачу. [JSON](assessment-stability.json) содержит результаты по всем routes/profiles/families; [наблюдения](../../data/evaluation/assessment-stability-observations.json) сохраняют определения профилей и SHA форм/ответов.

## Test-retest

| Фиксированный тип профиля | Пар | Raw agreement | Средний абсолютный Δscore | Pooled κ |
|---|---:|---:|---:|---:|
| Все профили |1920|0.860417|5.227927|0.722592|
| Attention boundary |480|0.566667|10.671750|0.400620|
| Basic boundary |384|0.968750|0.180990|0.953096|
| Weak skill |384|0.934896|4.404766|0.445663|
| Heterogeneous |384|0.940104|4.507760|-0.022341|
| Shallow |96|1.000000|4.670521|null|
| Blind guesser |96|1.000000|10.155208|null|
| Perfect control |96|1.000000|0.000000|1.000000|

**Pooled κ зависит от смеси requested grades.** Perfect control имеет pooled κ1 из-за четырёх разных grade labels; внутри каждого route он всегда PASS, поэтому κ вырожден и равен null. Показатель perfect control подтверждает только корректность полного метода. Для основных20-profile cohorts κ внутри24routes лежит от0.368421 до0.843750. Overall score correlation0.903009, но у attention-boundary только0.270911. Максимальный |Δscore|50.0. У143/480 route-profiles наблюдались одновременно PASS и FAIL. Отдельные стабильные extremes и overall agreement не доказывают устойчивость пограничных профилей.

## Item discrimination

384 route/competency/slot/family groups. Corrected item-rest correlation определена для377, у7нулевая item variance и correlation=null. Найдено49negative correlations и47nonpositive upper/lower differences; эти множества пересекаются. Rest исключает заработанные пункты самого item, а не его округлённый вклад в итоговый score.

Все49negative correlations относятся к `short` concept slot; диапазон от-0.178449 до-0.003940. В analysis/practice/mutation отрицательных correlations в этом cohort нет. Nonpositive upper/lower:41short,4practice,2mutation. Zero item variance:1short,4practice,2mutation. Средняя определённая corrected correlation по slot: short0.252578, analysis0.464685, practice0.419600, mutation0.413657. Это описательные показатели фиксированного responder mixture, не психометрические свойства реального населения.

Группировка49negative по grade и competency:

| Competency | Intern | Junior | Middle | Senior | Всего |
|---|---:|---:|---:|---:|---:|
| reliability |3|0|3|2|8|
| sql |5|0|2|0|7|
| testing |0|1|1|0|2|
| api |0|0|4|0|4|
| interpretation |1|1|0|0|2|
| data_quality |0|2|1|1|4|
| statistics |0|1|0|0|1|
| containers |1|0|0|0|1|
| networking |2|0|0|0|2|
| observability |0|0|1|1|2|
| web_security |2|2|2|0|6|
| accessibility |0|1|0|0|1|
| state |0|1|1|0|2|
| test_design |0|0|1|0|1|
| cryptography |0|1|0|0|1|
| authorization |0|0|1|2|3|
| incident_response |0|0|1|1|2|
| Всего |14|10|18|7|49|

По specialization: backend9,frontend6,qa8,devops8,data9,security9. Подробные family IDs и все flags находятся в JSON; банк и пороги по результату не переписаны.

## Последующая интерпретация и ограничения

Следующие причины — **post hoc hypotheses**, а не часть заранее заявленных результатов и не объяснение, снимающее flags. Профили намеренно имеют неоднородные способности по четырём competency. Whole-test rest включает другие темы; его связь с отдельной темой может ослабевать или менять знак при многомерных профилях. Shallow responder знает concept ledger и одновременно плохо решает data contracts: такая заданная смесь способна давать высокий short score при низком rest. Поэтому negative short correlations могут отражать как response-model mixture, так и слабую разделяющую силу конкретного item. Этот прогон не устанавливает причину и не доказывает, что flagged items качественны.

Zero-variance groups включают Junior SQL join, два closed-range task contexts, Middle modal-focus и один Intern JavaScript concept. Некоторые flawed methods случайно полностью выполняют отдельный контракт: это оставлено как фактический результат, а не исправлено ради более красивой discrimination. Нулевая дисперсия в этом cohort не означает бессмысленность задачи для всех людей.

43adjacent-grade/profile comparisons имеют более высокую modeled pass rate на более высоком requested grade. Например, у QA weak SQL profile Junior pass1.0 при Intern pass0.0: используемый flawed method фильтрует JOIN, но нарушает базовый aggregate фильтр. Это конкретная граница заданного method model, а не доказательство роста способности или корректной ordinal calibration банка. Разные contracts, случайный blind choice и attention variation требуют раздельного предметного анализа; flags не скрыты.

Дальнейшая проверка должна отдельно рассмотреть flagged concept families, обеспечить разнообразие методов ошибок для zero-variance contracts, изучить связи внутри конкретной competency и провести независимый человеческий pilot. Эти действия не выполнены в данном отчёте. Нельзя подстраивать cohort/пороги, затем называть те же данные независимой валидацией. Все повторные observations зависимы, bootstrap/significance для человеческой популяции не заявляются. Human test-retest, human item discrimination, IRT, время человека и соответствие реальным профессиональным грейдам остаются **NOT_MEASURED**.

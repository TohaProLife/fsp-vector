# Round 2: критический аудит domain engines

07.10.2026. Исходная реализация и авторский технический review. Это не внешний экспертный пилот, human gold, IRT calibration или сертификация безопасности. Frontend/design и основная БД в этом scope не менялись.

## Подтверждённые пробелы и исправления

1. У многих data-only practical families уровень менял преимущественно число строк. Сильные базовые ответы могли компенсировать провал сложных Senior concepts. Добавлены десять содержательных multi-step тем с отдельными Middle/Senior контрактами. SQL уже различался JOIN/window/NULL/fanout. Во всех четырёх практических темах Middle/Senior действует отдельный advanced floor: average60/75 и каждая тема≥50. Critical field error ограничивает задание40%, с публичным предупреждением. Старые сохранённые формы продолжают использовать свою rubric policy.
2. Не было прозрачного need→test пути. Pure need_blueprint выдаёт точные measured/unmeasured slices, priority и immutable snapshot SHA256. Need practice использует неизменный общий12-item blueprint/пороги, лишь упорядочивает competency blocks. Источник результата NEED_PRACTICE_OBSERVED; context.category_change=false, category_change_allowed=false, confirmed_grade=null. Formal engine сообщает лишь category_change_allowed; actual category_changed вычисляет backend по сохранённому предыдущему состоянию. Произвольные private need IDs не являются авторизацией: API использует доступную опубликованную вакансию или собственное приглашение.
3. PRACTICE_OBSERVED мог закрывать formal required gate при strength0.6. Теперь required admission и required C используют только ASSESSMENT_VERIFIED в правильной specialization/grade scope. Employer manual review/FSP/declaration/need practice не заменяют formal proof. Default minimum0.5; explicit required_min_strength может только повысить минимум.
4. Weighted C позволял маскировать слабый required множеством nice-to-have. C ограничен сверху weakest formal required+0.25. Это явная policy, не обученная модель. Веса55/20/10/5/5/5 сохраняются, gates не ослаблялись для роста benchmark score.
5. Freshness не учитывала объективную короткую практику. Допускается только scored60–100, objectively_graded/objective scope, нужный skill/spec, active source, timestamp от0 до90 дней. Practice A bonus≤0.25, то есть≤1.25 итогового пункта, уменьшается с возрастом. Категория/формальный required C не меняются. Unknown/manual/revoked/foreign/future/old observations не усиливают A.
6. Извлечение ошибочно переносило отрицание между соседними навыками и теряло отрицание коллективного списка. Исправлены реальные случаи «Python обязателен и SQL не требуется» и «Не требуются Python, SQL и Docker». Quote offsets сохраняются. Это ограниченный rules draft; свободная речь, произвольные неоднозначности и реальные вакансии не валидированы.
7. Counterfactual helper возвращает собственному кандидату условные действия без изменения profile/gates. Навыки/будущий экзамен не получают вымышленных score deltas. Точный delta считается лишь для допустимого изменения нестрогого предпочтения с повторным применением тех же gates. Непроверяемый навык явно имеет bank_supported=false.
8. Final API audit нашёл `candidate_projection(company=None)` в matcher: он удалял даже need practice текущей компании. Backend передаёт реальную компанию; engine теперь самостоятельно проверяет company_id, исключая foreign/missing company observations из C/A и explanations. Применяется даже при полном corpus. Global weekly practice без company binding остаётся отдельным допустимым source. A/B tests проверяют вклад только владельцу, отсутствие чужих observations/reasons, fail-closed missing scope и невозможность заменить required formal proof.
9. Добавлен отдельный explicit-label loader `evaluation.external` для anonymous observed corpus + явных immutable labels. Нет пересчёта labels из synthetic generator/scorer. Duplicate JSON keys/IDs/pairs, missing/unknown labels, malformed types/nonfinite values и latent/contact fields отвергаются. Empty/zero-eligible/zero-IDCG queries сохраняются; null metric имеет defined/undefined/retained count. Human origin/count — предоставленные декларации, origin_independently_verified=false; наличием importer не заявляется выполненный human pilot.
10. Browser probe выявил пропуск exact measured concept phrases, ложное направление Security внутри Web security и неверный required для списка «JavaScript concepts и Доступность будут плюсом». Canonical phrases распознаются целиком, longest-match не расширяет JavaScript concepts до JavaScript. Skill spans исключены из role matching; общий suffix распространяется лишь по bare connected list, предикат соседнего навыка прерывает перенос. Отдельная Security роль после Web security остаётся видимой и даёт ambiguity. Unsupported salary «180–240тысячрублей» и отсутствующий employment остаются unknown; requires_confirmation и точные quote offsets сохранены.
11. Официальный QA B1 подтвердил дефект FSP admission: mismatch scope/неизвестная дисциплина обнуляли спортивный бонус. V3 даёт всем valid achievements равную base0.8 + optional context0.2; gates/source/dedup/placement/freshness/потолокF5 сохраняются. Коэффициенты и basis видны в breakdown/reasons, policy author_initial. Это контекстный спортивный сигнал, не доказательство компетенции.
12. Официальный QA B4 выявил отсутствие explicit same-profile test-retest и item discrimination. Добавлены заранее фиксированный protocol/seed и public-condition behavior responders; ordinary grader выдаёт raw requested-grade либо UNCONFIRMED. Негативные результаты сохраняются; подробнее `evaluation/reports/assessment-stability.md`. Все17 QA conclusions описаны в `evaluation/EXPERT-QA-ENGINE-AUDIT.md`.

## Проверки

Команды из корня PowerShell:

```powershell
$env:PYTHONPATH='services/api;.'
.venv/Scripts/python.exe -m unittest discover -s services/api/tests/engines -v
.venv/Scripts/python.exe -m evaluation.generate_data --population 3000
.venv/Scripts/python.exe -m evaluation.run --seeds 100
```

77 domain/parser/metric tests PASS. 2400 forms /28800 items,186 manifest families,0 oracle failures. Data solvers получают только публичный контракт/данные и не импортируют генераторы/oracles. Для SQL дополнительная Python grouping проверка; для subset optimisation генератор использует combinations, reference solver — bit masks; для grants reference пересматривает предшествующие события, генератор поддерживает текущее состояние. Choice checks опираются на авторский ledger и не называются независимым human semantic review.

Свежий assessment seed диапазон400003–400022:480 forms/5760 items,0 failures. Все960 попыток с пропущенной одной сложной темой отклонены, хотя общий score мог быть91.67. Все240 «generic-only» попыток отклонены. Negative unit cases проверяют критическую ошибку каждого из22 advanced families, включая две SQL families; extra keys, bool/number, depth/text/large-number границы, DTO/private context privacy и старую stored policy. У параметризации конечное множество методов; знание полного public reference method даёт100% на программной симуляции. Прямой перенос старого literal key: pass0/100, mean22.834; адаптация старых choice labels: pass0/100, mean40.916. Это заданный attacker experiment, не human/LLM устойчивость.

Exposure:1152 observations, least-seen выбор в совместимом двухсценарном concept pool; оба варианта показаны до повторов, частоты сбалансированы. Data families сейчас не ротируются между альтернативными алгоритмами. Human matched-form equivalence, differential item functioning и время решения NOT_MEASURED; 40-minute duration и thresholds остаются author_initial.

## Подбор: полные результаты и потери gates

| Split / baseline | P@5 | nDCG@10 end-to-end | nDCG@10 eligible | Recall |
|---|---:|---:|---:|---:|
| Previously seen synthetic: full neutral, FSP v3 |0.9300|0.7284|0.9671|0.5971|
| Previously seen synthetic: random eligible |0.8867|0.6742|0.8934|тот же pool|
| Locked-seed synthetic holdout: full neutral |0.8967|0.7055|0.9585|0.5889|
| Locked-seed synthetic holdout: random eligible |0.8733|0.6637|0.9023|тот же pool|
| Holdout: full CPU TF-IDF |0.8967|0.7046|0.9574|тот же pool|
| Holdout: without competencies C |0.8633|0.6487|0.8807|тот же pool|
| Holdout: without assessment T |0.9133|0.7096|0.9628|тот же pool|
| Holdout: without FSP F |0.8967|0.7054|0.9583|тот же pool|
| Holdout: without required-evidence gate, evaluation only |0.9433|0.8948|0.9585|расширенный pool|

Каждый split60×20=1200 пар. Latent rubric не вызывает scorer и не использует его веса/FSP, но имеет общий synthetic generator/авторов. Human labelers=0. Holdout seed2026101107 зафиксирован до измерения; критерии под его результаты не подгонялись. Bootstrap intervals по synthetic queries находятся в JSON и не характеризуют неопределённость реального рынка.

Gate breakdown: ранее виденный split исключил231/570 программно relevant пар; holdout236/569. Во всех этих исключениях недостаточно формального evidence по required skills. Это реальная потеря recall, включая latent-qualified с missing observed evidence; высокая eligible nDCG её не устраняет. Gate-only ablation сохраняет privacy/account/category/conditions, запускается только в evaluation и не меняет default admission.

На holdout удаление T улучшает nDCG на0.0041; FSP эффект лишь0.0001; TF-IDF ухудшает end-to-end nDCG на0.0009. FSP v3 изменил seen end-to-end/eligible до0.7284/0.9671, но holdout full metrics не улучшились. Эти результаты не подтверждают оптимальность исходных весов или пользу каждого компонента. Веса сохраняются как прозрачная исходная policy до независимой разметки и калибровки; TF-IDF остаётся optional/default disabled.

150 узких extraction templates:900/900 field checks,0 negative-as-required,0 bad offsets. Дополнительно14 adverse skill statements:14/14 и четыре role/unknown-field cases:4/4, включая точный browser probe; три различных description→need blueprint примера. Это team-authored synthetic coverage, не независимый free-text human holdout.

Explicit-label CLI проверен на заранее заданном fictional adverse примере3queries/4pairs, human_labelers=0: P@5=0.066667, end-to-end nDCG=0.5 (defined2/undefined1), eligible nDCG=1 (defined1/undefined2), recall=0.5 (defined2/undefined1); zero-eligible query=1. Пример демонстрирует корректность удержания сложных/пустых запросов и denominator, не силу продукта. Input/corpus/labels SHA находятся в отдельном report; immutable loaded-data mutation отвергается. Команда/формат: `evaluation/EXTERNAL-LABELS.md`.

QA B4:192 distinct forms,120 fixed specialization profiles,3840 administrations/46080 responses/1920 A/B pairs. Overall raw agreement0.860417 и |Δscore|5.227927; pooledκ0.722592 зависит от смеси requested grades и не используется как headline профессиональной стабильности. Within-routeκ0.368421–0.843750; attention-boundary agreement0.566667.143/480 route-profiles получили и PASS, и FAIL.384item-family groups:49negative item-rest (всеshort),47nonpositive upper/lower,7zero variance/null;43non-monotonic grade flags. Банк/пороги/профили не менялись под эти результаты. Post hoc гипотезы о multidimensional response mixture не снимают flags и не являются доказательством качества. Подробная группировка/ограничения — `evaluation/reports/assessment-stability.md`; human stability/discrimination остаются NOT_MEASURED.

## Остаточные ограничения

Final PostgreSQL smoke выявил превышение `MatchRun.algorithm_version VARCHAR(80)` прежним идентификатором. Компактная версия `vector-match-55-20-10-5-5-5-v3-fsp-base-weakest-formal-company-semantic-neutral` занимает 79 символов; optional `cpu-tfidf` вариант — 72. Изменена только метка версии: формула, gates, FSP coefficients, locked протокол/профили, банк и пороги сохранены. Domain semantic test проверяет длину фактического результата обоих режимов; persisted/public PostgreSQL regression проверяется отдельным backend integration test. Отчёты пересозданы с прежними seed.

- Соответствие bounded-data score реальным Intern–Senior грейдам, качество найма, fair time budgets и психометрическая сопоставимость форм на людях не измерены.
- Общие короткие analysis slots остаются базовыми; сложные practical floors устраняют найденный bypass, но не заменяют длительную инженерную работу/внешний code runner.
- Need practice покрывает лишь exact measured skills банка. Python, React, PostgreSQL-specific implementation, Docker/Kubernetes implementation автоматически не подтверждаются.
- Rule extraction требует подтверждения человеком; произвольная лингвистика и currency conversion не поддерживаются полноценно.
- Synthetic observation fixtures явно маркированы SYNTHETIC_SEED/is_demo. Actual API identity/privacy/ownership/lifecycle интеграцию проверяет отдельный backend/root audit.
- Public DTO/JSON/SQL bounded checks — технические инварианты. Это не production security certification и не обещание предотвращения внешней помощи.

Актуальные machine-readable measured results/source SHA: `evaluation/reports/latest.json`; dataset SHA: `data/dataset-manifest.json` и `data/evaluation/dataset-manifest.json`. Исходники остаются локальными/приватными, код конкурентов не копировался.

# Измеренные результаты FSP Vector

Дата: 2026-10-11T13:41:36.223297+00:00. Python 3.14.6; Windows AMD64.

Это программная проверка и синтетическая симуляция. Человеческий пилот, реальный найм и эмпирическая калибровка НЕ измерены.

## Корректность банка
2400 форм × 12 заданий: 28800 проверок; 0 ошибок. Независимых data-solver checks: 19200; SQL группировок: 1200. Choice ledger checks (9600) подтверждают структуру/ключи авторского ledger, не независимую человеческую правильность и сложность.

## Подбор

| Модель | Precision@5 | nDCG@10 end-to-end | nDCG@10 eligible |
|---|---:|---:|---:|
| random_eligible | 0.8867 | 0.6742 | 0.8934 |
| keyword_all | 0.6867 | 0.6887 | 0.8967 |
| strong_category_test | 0.88 | 0.6748 | 0.8953 |
| full_neutral | 0.93 | 0.7284 | 0.9671 |
| full_cpu_tfidf | 0.9267 | 0.7295 | 0.9687 |
| without_competencies | 0.8867 | 0.6742 | 0.8954 |
| without_assessment | 0.93 | 0.7279 | 0.9663 |
| without_preferences | 0.93 | 0.7284 | 0.9671 |
| without_freshness | 0.93 | 0.7232 | 0.9607 |
| without_semantic | 0.93 | 0.7284 | 0.9671 |
| without_fsp | 0.93 | 0.7249 | 0.9627 |
| without_required_evidence_gate | 0.9633 | 0.9065 | 0.9671 |

## Locked-seed synthetic holdout

| Модель | Precision@5 | nDCG@10 end-to-end | nDCG@10 eligible |
|---|---:|---:|---:|
| random_eligible | 0.8733 | 0.6637 | 0.9023 |
| keyword_all | 0.74 | 0.7042 | 0.8915 |
| strong_category_test | 0.8667 | 0.6519 | 0.8869 |
| full_neutral | 0.8967 | 0.7055 | 0.9585 |
| full_cpu_tfidf | 0.8967 | 0.7046 | 0.9574 |
| without_competencies | 0.8633 | 0.6487 | 0.8807 |
| without_assessment | 0.9133 | 0.7096 | 0.9628 |
| without_preferences | 0.8967 | 0.7055 | 0.9585 |
| without_freshness | 0.9 | 0.7037 | 0.9561 |
| without_semantic | 0.8967 | 0.7055 | 0.9585 |
| without_fsp | 0.8967 | 0.7054 | 0.9583 |
| without_required_evidence_gate | 0.9433 | 0.8948 | 0.9585 |

Holdout seed=2026101107; recall=0.5889; excluded relevant pairs={'relevant_pairs': 569, 'excluded_relevant_pairs': 236, 'reason_counts': {'required_evidence_missing': 236}, 'multiple_reasons_per_pair_possible': True}. Метки программные, не human gold; пороги после этого holdout не подстраивались.

## Round 2 domain adversarial evaluation

{
  "status": "PASS",
  "assessment_fresh_seed_forms": 480,
  "assessment_fresh_seed_items": 5760,
  "one_advanced_topic_missing_blocks_pass": 960,
  "generic_only_shortcut_blocks_pass": 240,
  "advanced_family_distinct_correct_answers": {
    "advanced.event-ledger.middle": 115,
    "advanced.event-ledger.senior": 29,
    "advanced.grant-replay.middle": 80,
    "advanced.grant-replay.senior": 76,
    "advanced.key-rotation.middle": 20,
    "advanced.key-rotation.senior": 20,
    "advanced.modal-focus.middle": 2,
    "advanced.modal-focus.senior": 8,
    "advanced.retry-deadline.middle": 3,
    "advanced.retry-deadline.senior": 5,
    "advanced.risk-cover.middle": 40,
    "advanced.risk-cover.senior": 40,
    "advanced.rollout-capacity.middle": 17,
    "advanced.rollout-capacity.senior": 15,
    "advanced.slo-windows.middle": 19,
    "advanced.slo-windows.senior": 19,
    "advanced.stratified-effect.middle": 40,
    "advanced.stratified-effect.senior": 40,
    "advanced.ui-replay.middle": 27,
    "advanced.ui-replay.senior": 29,
    "data.sql-latest_per_customer": 6,
    "data.sql-refund_preaggregate": 6
  },
  "concept_exposure_observations": 1152,
  "concept_exposure_rule": "least_seen_within_compatible_two_scenario_pool; data_family_exposure_not_rotated",
  "adverse_extraction_cases": 14,
  "adverse_extraction_passed": 14,
  "adverse_extraction_role_cases": 4,
  "adverse_extraction_role_passed": 4,
  "need_description_examples": 3,
  "adverse_matching_checks": 6,
  "adverse_matching_passed": 6,
  "failures": [],
  "human_grade_validity": "NOT_MEASURED",
  "parallel_form_equivalence_on_people": "NOT_MEASURED",
  "fairness_on_response_time": "NOT_MEASURED"
}

## Официальный QA B4: synthetic test-retest и разделяющая сила

Протокол зафиксирован до измерения: seed2026100704,20 fixed profiles/специализацию,8 independent forms/route. Ответы вычисляются по public conditions, баллы назначает ordinary grade_form. Raw requested-grade/UNCONFIRMED не скрывает неуспех сохранённой предыдущей категорией. Подробности: [assessment-stability.json](assessment-stability.json), [locked protocol](../ASSESSMENT-STABILITY-PROTOCOL.md), [все17 QA conclusions](../EXPERT-QA-ENGINE-AUDIT.md).
{
  "protocol_id": "vector-synthetic-retest-v1",
  "protocol_sha256": "d3f67449b7d8c1d4f4218d40e0263f82882f7d12d31613bf113fb7fdad4347d7",
  "locked_seed": 2026100704,
  "distinct_forms": 192,
  "profile_attempt_administrations": 3840,
  "item_responses": 46080,
  "fixed_profiles": 120,
  "repeats_per_route_profile": 8,
  "overall": {
    "pairs": 1920,
    "agreement": 0.860417,
    "expected_agreement": 0.496831,
    "kappa": 0.722592,
    "mean_signed_score_difference": -0.463135,
    "mean_absolute_score_difference": 5.227927,
    "max_absolute_score_difference": 50.0,
    "score_correlation": 0.903009,
    "confusion": {
      "UNCONFIRMED -> UNCONFIRMED": 1179,
      "UNCONFIRMED -> intern": 39,
      "UNCONFIRMED -> junior": 33,
      "UNCONFIRMED -> middle": 30,
      "UNCONFIRMED -> senior": 33,
      "intern -> UNCONFIRMED": 32,
      "intern -> intern": 175,
      "junior -> UNCONFIRMED": 35,
      "junior -> junior": 183,
      "middle -> UNCONFIRMED": 32,
      "middle -> middle": 64,
      "senior -> UNCONFIRMED": 34,
      "senior -> senior": 51
    }
  },
  "by_kind": {
    "attention_boundary": {
      "pairs": 480,
      "agreement": 0.566667,
      "expected_agreement": 0.277031,
      "kappa": 0.40062,
      "mean_signed_score_difference": -0.64425,
      "mean_absolute_score_difference": 10.67175,
      "max_absolute_score_difference": 50.0,
      "score_correlation": 0.270911,
      "confusion": {
        "UNCONFIRMED -> UNCONFIRMED": 109,
        "UNCONFIRMED -> intern": 27,
        "UNCONFIRMED -> junior": 26,
        "UNCONFIRMED -> middle": 26,
        "UNCONFIRMED -> senior": 26,
        "intern -> UNCONFIRMED": 19,
        "intern -> intern": 54,
        "junior -> UNCONFIRMED": 24,
        "junior -> junior": 57,
        "middle -> UNCONFIRMED": 29,
        "middle -> middle": 27,
        "senior -> UNCONFIRMED": 31,
        "senior -> senior": 25
      }
    },
    "basic_boundary": {
      "pairs": 384,
      "agreement": 0.96875,
      "expected_agreement": 0.33374,
      "kappa": 0.953096,
      "mean_signed_score_difference": 0.030417,
      "mean_absolute_score_difference": 0.18099,
      "max_absolute_score_difference": 5.56,
      "score_correlation": 0.972012,
      "confusion": {
        "UNCONFIRMED -> UNCONFIRMED": 169,
        "UNCONFIRMED -> middle": 2,
        "UNCONFIRMED -> senior": 5,
        "intern -> intern": 96,
        "junior -> junior": 96,
        "middle -> UNCONFIRMED": 2,
        "middle -> middle": 9,
        "senior -> UNCONFIRMED": 3,
        "senior -> senior": 2
      }
    },
    "guesser": {
      "pairs": 96,
      "agreement": 1.0,
      "expected_agreement": 1.0,
      "kappa": null,
      "mean_signed_score_difference": -1.094375,
      "mean_absolute_score_difference": 10.155208,
      "max_absolute_score_difference": 38.89,
      "score_correlation": 0.206359,
      "confusion": {
        "UNCONFIRMED -> UNCONFIRMED": 96
      }
    },
    "heterogeneous": {
      "pairs": 384,
      "agreement": 0.940104,
      "expected_agreement": 0.941413,
      "kappa": -0.022341,
      "mean_signed_score_difference": -0.806979,
      "mean_absolute_score_difference": 4.50776,
      "max_absolute_score_difference": 16.67,
      "score_correlation": 0.440633,
      "confusion": {
        "UNCONFIRMED -> UNCONFIRMED": 361,
        "UNCONFIRMED -> intern": 7,
        "UNCONFIRMED -> junior": 3,
        "intern -> UNCONFIRMED": 6,
        "junior -> UNCONFIRMED": 7
      }
    },
    "perfect": {
      "pairs": 96,
      "agreement": 1.0,
      "expected_agreement": 0.25,
      "kappa": 1.0,
      "mean_signed_score_difference": 0.0,
      "mean_absolute_score_difference": 0.0,
      "max_absolute_score_difference": 0.0,
      "score_correlation": null,
      "confusion": {
        "intern -> intern": 24,
        "junior -> junior": 24,
        "middle -> middle": 24,
        "senior -> senior": 24
      }
    },
    "shallow": {
      "pairs": 96,
      "agreement": 1.0,
      "expected_agreement": 1.0,
      "kappa": null,
      "mean_signed_score_difference": -1.267604,
      "mean_absolute_score_difference": 4.670521,
      "max_absolute_score_difference": 16.67,
      "score_correlation": 0.36624,
      "confusion": {
        "UNCONFIRMED -> UNCONFIRMED": 96
      }
    },
    "weak_skill": {
      "pairs": 384,
      "agreement": 0.934896,
      "expected_agreement": 0.882555,
      "kappa": 0.445663,
      "mean_signed_score_difference": -0.143307,
      "mean_absolute_score_difference": 4.404766,
      "max_absolute_score_difference": 16.67,
      "score_correlation": 0.19136,
      "confusion": {
        "UNCONFIRMED -> UNCONFIRMED": 348,
        "UNCONFIRMED -> intern": 5,
        "UNCONFIRMED -> junior": 4,
        "UNCONFIRMED -> middle": 2,
        "UNCONFIRMED -> senior": 2,
        "intern -> UNCONFIRMED": 7,
        "intern -> intern": 1,
        "junior -> UNCONFIRMED": 4,
        "junior -> junior": 6,
        "middle -> UNCONFIRMED": 1,
        "middle -> middle": 4
      }
    }
  },
  "route_profiles_with_mixed_raw_assignments": 143,
  "item_family_groups": 384,
  "item_flags": {
    "negative_corrected_correlation": 49,
    "nonpositive_upper_lower_separation": 47,
    "zero_item_variance": 7
  },
  "undefined_item_rest_correlations": 7,
  "nonmonotonic_grade_profile_comparisons": 43,
  "observations_sha256": "aa7c2ac976e07ddc723fcf871677af9edd8a4fde1198870e3a1de7fc72d6b956",
  "report_path": "evaluation/reports/assessment-stability.json",
  "observations_path": "data/evaluation/assessment-stability-observations.json",
  "human_test_retest": "NOT_MEASURED",
  "human_item_discrimination": "NOT_MEASURED",
  "interpretation": "Fixed public-method profiles evaluated by ordinary grader. Behavior mixture/attention propensities are author assumptions, not learned human response probabilities; raw assignments do not use persisted prior-grade retention."
}

Нулевые дисперсии и κ degeneracy дают null. Негативные item-rest/upper-lower и non-monotonic grade flags сохранены, пороги/response model под результат не подстраивались. Это модельная симуляция; человеческие test-retest и item discrimination NOT_MEASURED.

## Explicit independent-label loader

`evaluation.external` принимает отдельный anonymous observed corpus и явные labels, считает SHA входа/corpus/labels, отклоняет duplicate/missing/unknown IDs и latent/contact fields. Metadata human origin остаётся декларацией, не подтверждённым пилотом.
Фиктивный adverse пример: 3 queries/4 pairs; zero-eligible=1; human_labelers=0; P@5=0.066667. Все запросы сохранены, zero-IDCG метрики null с явным count. Это проверка loader/метрик, не независимый human benchmark.

60 queries × 20 пар = 1200 программных synthetic labels, human labelers=0. Eligible mean=6.167; retrieval recall=0.5971; gate violations=0.
TF-IDF ablation Δ nDCG@10=0.0011; модель сохраняет статус optional uncalibrated lexical baseline. Положительный модельный эффект не доказывает реальную эффективность.

## Перенос старого ответа

| Режим | Средний score | Pass rate |
|---|---:|---:|
| fixed_form_prior_key | 100.0 | 1 |
| two_form_bank_prior_key | 70.255 | 0.5 |
| parameterized_prior_literal_key | 22.834 | 0 |
| parameterized_prior_choice_labels | 40.916 | 0 |
| complete_public_reference_method | 100.0 | 1 |

Узкий перенос старого ответа измерен программно. Знание полного метода/банка позволяет решить все задания: параметризация не является гарантией против внешней помощи. A/B сравнение моделируется честным чередованием двух форм; это не наблюдение на людях.

## Извлечение
150 ограниченных синтетических шаблонов, field checks=900, accuracy=1.0; отрицательные как required=0; неверные offsets=0. Независимый human holdout: NOT_MEASURED.

## Ограничения

- Labels синтетические и программные, общий автор данных и продукта. Они не называются human gold.
- На профессиональных грейдах и людях пороги70/50/60 и difficulty labels ещё не валидированы.
- Параметризация не защищает от знания полного метода, полного банка или внешнего помощника.
- CPU TF-IDF вычисляет lexical similarity; глубокая семантика и найм не измерены.
- Нагрузочные API, Windows runner и browser E2E проверяются отдельным интеграционным аудитом.

Воспроизведение: `python -m evaluation.run --seeds 100`; результаты JSON содержат bootstrap интервалы, версии и окружение.

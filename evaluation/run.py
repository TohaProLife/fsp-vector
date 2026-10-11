"""Reproducible evaluation of ORIGINAL synthetic/programmatic evidence.

Run from repository root: python -m evaluation.run --seeds 100.
No human result, empirical IRT calibration or real hiring success is fabricated.
"""

import argparse
import csv
import hashlib
import json
import math
import platform
import random
import statistics
import sys
import time
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
from collections import Counter

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"services"/"api"))
from app.engines.assessment import create_form,public_form,grade_form
from app.engines.bank import BANK_VERSION,family_manifest
from app.engines.taxonomy import SPECIALIZATIONS,GRADES
from app.engines.safe_sql import canonical_rows
from app.engines.matching import ALGORITHM_VERSION,rank_candidates,admission
from app.engines.seed import generate_population,generate_needs
from app.engines.extraction import extract_need
from app.engines.semantic import MODEL_VERSION
from evaluation.reference_solvers import reference_answer,independent_sql_rows

NOW=datetime(2026,10,7,9,0,tzinfo=timezone.utc)
SEED=941_007
HOLDOUT_SEED=2_026_101_107


def _dump(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8",newline="\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def assessment_correctness(seeds):
    count=0; data_checks=0; choice_checks=0; failures=[]; seen=set(); sql_checks=0
    started=time.perf_counter()
    for specialization in SPECIALIZATIONS:
        for grade in GRADES:
            for seed in range(seeds):
                form=create_form(specialization,grade,seed=seed)
                public=public_form(form)
                answers={item["id"]:reference_answer(item) for item in public["items"]}
                result=grade_form(form,answers)
                count+=len(form["items"])
                for private in form["items"]:
                    seen.add(private["family_id"])
                    if private["type"]=="single_choice": choice_checks+=1
                    else: data_checks+=1
                if not result["passed"] or result["score"]!=100:
                    failures.append({"specialization":specialization,"grade":grade,"seed":seed,"score":result["score"]})
                for item in public["items"]:
                    if item["type"]=="sql":
                        expected=independent_sql_rows(item)
                        private=next(row for row in form["items"] if row["id"]==item["id"])
                        sql_checks+=1
                        if canonical_rows(expected)!=canonical_rows(private["_oracle"]["rows"]): failures.append({"item":item["title"],"seed":seed,"problem":"independent_sql_oracle_mismatch"})
    return {"forms":len(SPECIALIZATIONS)*len(GRADES)*seeds,"seeds_per_track_grade":seeds,"items_checked":count,"independent_data_solver_checks":data_checks,"choice_structural_author_ledger_checks":choice_checks,"independent_SQL_grouping_checks":sql_checks,"distinct_families_exercised":len(seen),"manifest_families":len(family_manifest()),"failures":failures,"seconds":round(time.perf_counter()-started,3),"status":"PASS" if not failures else "FAIL","human_semantic_review":"NOT_MEASURED","grade_validity":"NOT_MEASURED","form_equivalence_on_people":"NOT_MEASURED"}


def _transfer(old_public,old_answers,new_public,adapt_choice_labels=False):
    old={(item["competency"],item["slot"]):item for item in old_public["items"]}
    answers={}
    for item in new_public["items"]:
        previous=old.get((item["competency"],item["slot"]))
        if not previous: continue
        answer=old_answers[previous["id"]]
        if item["type"]=="single_choice" and adapt_choice_labels:
            label=next(option["label"] for option in previous["options"] if option["id"]==answer)
            matching=next((option["id"] for option in item["options"] if option["label"]==label),None)
            answer=matching or "prior_label_not_present"
        answers[item["id"]]=answer
    return answers


def leakage_experiment(forms=100):
    rows={name:[] for name in ("fixed_form_prior_key","two_form_bank_prior_key","parameterized_prior_literal_key","parameterized_prior_choice_labels","complete_public_reference_method")}
    old=create_form("backend","middle",seed=909)
    old_public=public_form(old); key={item["id"]:reference_answer(item) for item in old_public["items"]}
    for seed in range(forms):
        other=create_form("backend","middle",seed=10000+seed)
        new_public=public_form(other)
        rows["fixed_form_prior_key"].append(grade_form(old,key))
        bank=old if seed%2==0 else other
        rows["two_form_bank_prior_key"].append(grade_form(bank,_transfer(old_public,key,public_form(bank),True)))
        rows["parameterized_prior_literal_key"].append(grade_form(other,_transfer(old_public,key,new_public)))
        rows["parameterized_prior_choice_labels"].append(grade_form(other,_transfer(old_public,key,new_public,True)))
        rows["complete_public_reference_method"].append(grade_form(other,{item["id"]:reference_answer(item) for item in new_public["items"]}))
    result={name:{"n":len(results),"mean_score":round(statistics.mean(row["score"] for row in results),3),"pass_rate":round(statistics.mean(int(row["passed"]) for row in results),3)} for name,results in rows.items()}
    return {"method":"Direct transfer of one prior correct key by competency/slot; with and without adapting choice labels. Public algorithm solver supplies an explicit strong attacker upper bound.","results":result,"human_pass_rate_inflation":"NOT_MEASURED","time_to_solve":"NOT_MEASURED","llm_attack":"NOT_MEASURED","interpretation":"Узкий перенос старого ответа измерен программно. Знание полного метода/банка позволяет решить все задания: параметризация не является гарантией против внешней помощи. A/B сравнение моделируется честным чередованием двух форм; это не наблюдение на людях."}


def gold_label(need,candidate):
    """Independent predeclared latent rubric, does not call rank/admission/weights."""
    latent=candidate["_latent"]
    if not candidate["published"] or latent["specialization"]!=need["specialization"] or latent["grade"]!=need["grade"]: return 0
    if latent["work_format"]!=need["work_format"] or latent["salary_min"]>need["salary_to"]: return 0
    required=need["required_skills"]
    values=[latent["mastery"].get(skill,0.) for skill in required]
    if not values or min(values)<.45: return 1
    if min(values)>=.75: return 3
    if statistics.mean(values)>=.6: return 2
    return 1


def _precision(order,labels,k): return sum(labels.get(value,0)>=2 for value in order[:k])/k


def _ndcg(order,labels,k):
    ideal=sorted(labels.values(),reverse=True)[:k]
    idcg=sum((2**value-1)/math.log2(index+2) for index,value in enumerate(ideal))
    if not idcg:return None
    dcg=sum((2**labels.get(value,0)-1)/math.log2(index+2) for index,value in enumerate(order[:k]))
    return dcg/idcg


def _bootstrap(values,rng):
    if not values:return None
    means=sorted(statistics.mean(rng.choices(values,k=len(values))) for _ in range(1000))
    return [round(means[25],4),round(means[975],4)]


def matching_evaluation(seed=SEED,holdout=False):
    rng=random.Random(seed);population=generate_population(3000,seed=seed,include_latent=True);needs=generate_needs(60,seed=seed+1)
    names=["random_eligible","keyword_all","strong_category_test","full_neutral","full_cpu_tfidf",*["without_"+key for key in ("competencies","assessment","preferences","freshness","semantic","fsp")],"without_required_evidence_gate"]
    pairs=[];query_metrics={key:[] for key in names};eligible_counts=[];retrieval_recalls=[];gate_violations=0;timing=[];gold_queries=[];excluded_relevant=Counter();excluded_pairs=0;relevant_pairs=0
    for need in needs:
        # Stratified collection is selected BEFORE the matcher: 12 candidates in
        # intended population/format and 8 counterexamples, not the engine's top20.
        same=[row for row in population if row["_latent"]["specialization"]==need["specialization"] and row["_latent"]["grade"]==need["grade"] and row["_latent"]["work_format"]==need["work_format"]]
        good=rng.sample(same,min(12,len(same)))
        other=[row for row in population if row not in good]
        selected=good+rng.sample(other,20-len(good));rng.shuffle(selected)
        labels={row["id"]:gold_label(need,row) for row in selected}
        observed=[{key:value for key,value in row.items() if key!="_latent"} for row in selected]
        for row in selected:pairs.append({"need_id":need["id"],"candidate_id":row["id"],"label":labels[row["id"]],"reference_kind":"PROGRAMMATIC_SYNTHETIC_LATENT_RUBRIC"})
        eligible=[row for row in observed if admission(need,row)["eligible"]]
        eligible_ids={row["id"] for row in eligible};eligible_counts.append(len(eligible))
        relevant={key for key,value in labels.items() if value>=2}
        relevant_pairs+=len(relevant)
        for row in observed:
            if row["id"] in relevant and row["id"] not in eligible_ids:
                excluded_pairs+=1;excluded_relevant.update(admission(need,row)["reasons"])
        if relevant:retrieval_recalls.append(len(relevant&eligible_ids)/len(relevant))
        random_order=sorted(eligible_ids);rng.shuffle(random_order)
        needed=set(need["required_skills"]+need["skills"])
        keyword_order=[row["id"] for row in sorted(observed,key=lambda row:(-len(needed&set(row["skills"])),row["id"]))]
        strong=[row["id"] for row in sorted(eligible,key=lambda row:(-row["score"],row["id"]))]
        before=time.perf_counter();neutral=rank_candidates(need,observed,NOW);timing.append(time.perf_counter()-before)
        cpu=rank_candidates(need,observed,NOW,semantic_enabled=True)
        neutral_order=[row["candidate_id"] for row in neutral];cpu_order=[row["candidate_id"] for row in cpu]
        for row in neutral:gate_violations+=int(row["candidate_id"] not in eligible_ids)
        orders={"random_eligible":random_order,"keyword_all":keyword_order,"strong_category_test":strong,"full_neutral":neutral_order,"full_cpu_tfidf":cpu_order}
        # Ablate one calculated component using the exact same eligible set. A
        # constant rescaling of remaining weights does not change this ordering.
        for component in ("competencies","assessment","preferences","freshness","semantic","fsp"):
            orders["without_"+component]=[row["candidate_id"] for row in sorted(neutral,key=lambda row:(-(row["score"]-row["breakdown"][component]["points"]),row["candidate_id"]))]
        # Evaluation-only gate ablation preserves publication/account/category/
        # preferences/company constraints. Production defaults are untouched.
        relaxed={**need,"require_verified_skills":False}
        orders["without_required_evidence_gate"]=[row["candidate_id"] for row in rank_candidates(relaxed,observed,NOW)]
        for name,order in orders.items():
            eligible_labels={key:value for key,value in labels.items() if key in eligible_ids}
            query_metrics[name].append({"precision5":_precision(order,labels,5),"ndcg10_end_to_end":_ndcg(order,labels,10),"ndcg10_eligible":_ndcg([value for value in order if value in eligible_ids],eligible_labels,10)})
        gold_queries.append({"need":need,"candidates":observed,"labels":labels})
    file_prefix="matching-holdout" if holdout else "matching"
    _dump(ROOT/"data"/"evaluation"/(file_prefix+"-benchmark.json"),{"version":"synthetic-team-model-v2","split":"locked_seed_holdout" if holdout else "previously_seen_synthetic_benchmark","seed":seed,"queries":gold_queries,"reference_kind":"PROGRAMMATIC_SYNTHETIC_LATENT_RUBRIC","human_labelers":0,"limitation":"Стратифицированная вымышленная популяция; независимая функция latent rubric, но общие авторы и искусственный генератор. Не human gold и не реальный рынок."})
    with (ROOT/"data"/"evaluation"/(file_prefix+"-labels.csv")).open("w",encoding="utf-8",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=list(pairs[0]),lineterminator="\n");writer.writeheader();writer.writerows(pairs)
    aggregates={}
    for name,results in query_metrics.items():
        aggregates[name]={}
        for metric in results[0]:
            values=[row[metric] for row in results if row[metric] is not None]
            aggregates[name][metric]={"mean":round(statistics.mean(values),4),"bootstrap95":_bootstrap(values,rng),"queries":len(values),"idcg_zero_excluded":len(results)-len(values)}
    return {"split":"locked_seed_holdout" if holdout else "previously_seen_synthetic_benchmark","seed":seed,"population_size":3000,"needs":60,"labels":len(pairs),"labels_kind":"PROGRAMMATIC_SYNTHETIC_LATENT_RUBRIC","human_labelers":0,"rubric":"0=incompatible category/visibility/conditions;1=uncertain/weak latent requirements;2=latent mean>=.6,min>=.45;3=min>=.75; excludes ranking weights and FSP","baselines":aggregates,"ablation_method":"single_feature_removed_from_actual_calculated_score_same_gates_no_retuning; required_gate_only_removed_in_evaluation_preserving_privacy_category_conditions","gate_failure_breakdown":{"relevant_pairs":relevant_pairs,"excluded_relevant_pairs":excluded_pairs,"reason_counts":dict(sorted(excluded_relevant.items())),"multiple_reasons_per_pair_possible":True},"eligible_per_query_mean":round(statistics.mean(eligible_counts),3),"retrieval_recall_mean":round(statistics.mean(retrieval_recalls),4),"gate_violations":gate_violations,"matching_ms_p95_20_candidates":round(sorted(timing)[int(.95*(len(timing)-1))]*1000,3),"ml_ablation_delta_ndcg10":round(aggregates["full_cpu_tfidf"]["ndcg10_end_to_end"]["mean"]-aggregates["full_neutral"]["ndcg10_end_to_end"]["mean"],4),"human_relevance_agreement":"NOT_MEASURED","real_hiring_quality":"NOT_MEASURED","limitations":["Model-based labels share a synthetic generator with observed candidates; independent score function does not make them human gold.","Twenty profiles per query intentionally include category/condition counterexamples; fixed-K precision penalizes small eligible sets.","Admission can exclude latent-qualified candidates with missing observed evidence; retrieval recall reports this loss.","Bootstrap intervals are over synthetic queries and cannot represent uncertainty of the real market.","The held-out seed checks generator generalization; it is not independent real-world/human gold."]}


def extraction_evaluation():
    cases=[]
    specs=[("backend","backend"),("frontend","frontend"),("QA","qa"),("DevOps","devops"),("аналитик данных","data"),("Security","security")]
    words=[("Python","Python"),("SQL","SQL"),("React","React"),("Docker","Docker"),("Kafka","Kafka")]
    for index in range(150):
        label,spec=specs[index%6];raw,skill=words[index%5];grade=GRADES[index%4]
        grade_word="стажёр" if grade=="intern" else grade
        mode=index%3
        statement=f"{raw} обязателен." if mode==0 else f"{raw} желателен." if mode==1 else f"{raw} не требуется."
        text=f"Ищем {grade_word} {label}. {statement} Удалённо. 180–250 тыс RUB."
        cases.append({"text":text,"specialization":spec,"grade":grade,"skill":skill,"polarity":["required","preferred","excluded"][mode],"salary_from":180000,"salary_to":250000,"work_format":"remote"})
    matches=0;total=0;span_errors=0;negative_errors=0
    for case in cases:
        result=extract_need(case["text"])
        for key in ("specialization","grade","salary_from","salary_to","work_format"):
            total+=1;matches+=int(result[key]==case[key])
        field={"required":"required_skills","preferred":"preferred_skills","excluded":"excluded_skills"}[case["polarity"]]
        total+=1;matches+=int(case["skill"] in result[field])
        if case["polarity"]=="excluded":negative_errors+=int(case["skill"] in result["required_skills"])
        span_errors+=sum(span["quote"]!=case["text"][span["start"]:span["end"]] for span in result["source_spans"])
    _dump(ROOT/"data"/"evaluation"/"extraction-cases.json",{"cases":cases,"kind":"TEAM_AUTHORED_SYNTHETIC_TEMPLATES","human_labelers":0})
    return {"cases":len(cases),"field_checks":total,"correct":matches,"accuracy_on_templates":round(matches/total,4),"negative_as_required_errors":negative_errors,"source_span_errors":span_errors,"human_holdout":"NOT_MEASURED","limitation":"150 deterministic team-authored templates, limited vocabulary; no independent human or arbitrary-language generalization claim."}


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--seeds",type=int,default=100);args=parser.parse_args()
    sources={str(path.relative_to(ROOT)).replace("\\","/"):hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted((ROOT/"services"/"api"/"app"/"engines").glob("*.py"))}
    evaluation_sources={str(path.relative_to(ROOT)).replace("\\","/"):hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted((ROOT/"evaluation").glob("*.py"))}
    from evaluation.round2 import round2_evaluation
    from evaluation.stability import stability_evaluation
    report={"report_version":"vector-evaluation-2","generated_at":datetime.now(timezone.utc).isoformat(),"versions":{"bank":BANK_VERSION,"matching":ALGORITHM_VERSION,"optional_semantic":MODEL_VERSION,"source_sha256":sources},"environment":{"python":platform.python_version(),"system":platform.system(),"machine":platform.machine()},"assessment":assessment_correctness(args.seeds),"leakage":leakage_experiment(),"matching":matching_evaluation(),"matching_holdout":matching_evaluation(HOLDOUT_SEED,True),"round2":round2_evaluation(),"extraction":extraction_evaluation(),"not_measured":{"human_pilot":True,"human_grade_validity":True,"human_form_equivalence":True,"irt_empirical_calibration":True,"llm_attack_experiment":True,"real_hiring_outcome":True,"production_security_certification":True}}
    report["versions"]["evaluation_source_sha256"]=evaluation_sources
    report["assessment_stability"]=stability_evaluation()
    from evaluation.external import load_dataset,evaluate_dataset
    report["external_loader"]={"status":"AVAILABLE_EXPLICIT_LABELS","human_pilot":"NOT_MEASURED","declared_origin_independently_verified":False}
    report["external_example"]=evaluate_dataset(load_dataset(ROOT/"data"/"evaluation"/"external-example.json"),NOW)
    report["versions"]["dataset_sha256"]={str(path.relative_to(ROOT)).replace("\\","/"):hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted((ROOT/"data"/"evaluation").glob("*")) if path.is_file()}
    _dump(ROOT/"data"/"evaluation"/"dataset-manifest.json",{"version":"vector-evaluation-data-v1","line_endings":"LF","reference_kind":"PROGRAMMATIC_SYNTHETIC_LATENT_RUBRIC_AND_TEAM_TEMPLATES","human_labelers":0,"files":[{"path":path,"sha256":sha256} for path,sha256 in report["versions"]["dataset_sha256"].items() if not path.endswith("dataset-manifest.json")]})
    report["versions"]["dataset_sha256"]["data/evaluation/dataset-manifest.json"]=hashlib.sha256((ROOT/"data"/"evaluation"/"dataset-manifest.json").read_bytes()).hexdigest()
    report_path=ROOT/"evaluation"/"reports"/"latest.json";_dump(report_path,report)
    md=["# Измеренные результаты FSP Vector","",f"Дата: {report['generated_at']}. Python {report['environment']['python']}; {report['environment']['system']} {report['environment']['machine']}.","","Это программная проверка и синтетическая симуляция. Человеческий пилот, реальный найм и эмпирическая калибровка НЕ измерены.","","## Корректность банка",f"{report['assessment']['forms']} форм × 12 заданий: {report['assessment']['items_checked']} проверок; {len(report['assessment']['failures'])} ошибок. Независимых data-solver checks: {report['assessment']['independent_data_solver_checks']}; SQL группировок: {report['assessment']['independent_SQL_grouping_checks']}. Choice ledger checks ({report['assessment']['choice_structural_author_ledger_checks']}) подтверждают структуру/ключи авторского ledger, не независимую человеческую правильность и сложность.","","## Подбор","", "| Модель | Precision@5 | nDCG@10 end-to-end | nDCG@10 eligible |","|---|---:|---:|---:|"]
    for name,values in report["matching"]["baselines"].items():md.append(f"| {name} | {values['precision5']['mean']} | {values['ndcg10_end_to_end']['mean']} | {values['ndcg10_eligible']['mean']} |")
    md.extend(["","## Locked-seed synthetic holdout","","| Модель | Precision@5 | nDCG@10 end-to-end | nDCG@10 eligible |","|---|---:|---:|---:|"])
    for name,values in report["matching_holdout"]["baselines"].items():md.append(f"| {name} | {values['precision5']['mean']} | {values['ndcg10_end_to_end']['mean']} | {values['ndcg10_eligible']['mean']} |")
    md.extend(["",f"Holdout seed={HOLDOUT_SEED}; recall={report['matching_holdout']['retrieval_recall_mean']}; excluded relevant pairs={report['matching_holdout']['gate_failure_breakdown']}. Метки программные, не human gold; пороги после этого holdout не подстраивались.","","## Round 2 domain adversarial evaluation","",json.dumps(report["round2"],ensure_ascii=False,indent=2)])
    md.extend(["","## Официальный QA B4: synthetic test-retest и разделяющая сила","","Протокол зафиксирован до измерения: seed2026100704,20 fixed profiles/специализацию,8 independent forms/route. Ответы вычисляются по public conditions, баллы назначает ordinary grade_form. Raw requested-grade/UNCONFIRMED не скрывает неуспех сохранённой предыдущей категорией. Подробности: [assessment-stability.json](assessment-stability.json), [locked protocol](../ASSESSMENT-STABILITY-PROTOCOL.md), [все17 QA conclusions](../EXPERT-QA-ENGINE-AUDIT.md).",json.dumps(report["assessment_stability"],ensure_ascii=False,indent=2),"","Нулевые дисперсии и κ degeneracy дают null. Негативные item-rest/upper-lower и non-monotonic grade flags сохранены, пороги/response model под результат не подстраивались. Это модельная симуляция; человеческие test-retest и item discrimination NOT_MEASURED."])
    md.extend(["","## Explicit independent-label loader","","`evaluation.external` принимает отдельный anonymous observed corpus и явные labels, считает SHA входа/corpus/labels, отклоняет duplicate/missing/unknown IDs и latent/contact fields. Metadata human origin остаётся декларацией, не подтверждённым пилотом.",f"Фиктивный adverse пример: {report['external_example']['queries']} queries/{report['external_example']['pairs']} pairs; zero-eligible={report['external_example']['zero_eligible_queries']}; human_labelers=0; P@5={report['external_example']['baselines']['full_engine']['precision5']['mean']}. Все запросы сохранены, zero-IDCG метрики null с явным count. Это проверка loader/метрик, не независимый human benchmark."])
    md.extend(["",f"60 queries × 20 пар = 1200 программных synthetic labels, human labelers=0. Eligible mean={report['matching']['eligible_per_query_mean']}; retrieval recall={report['matching']['retrieval_recall_mean']}; gate violations={report['matching']['gate_violations']}.",f"TF-IDF ablation Δ nDCG@10={report['matching']['ml_ablation_delta_ndcg10']}; модель сохраняет статус optional uncalibrated lexical baseline. Положительный модельный эффект не доказывает реальную эффективность.","","## Перенос старого ответа","","| Режим | Средний score | Pass rate |","|---|---:|---:|"])
    for name,values in report["leakage"]["results"].items():md.append(f"| {name} | {values['mean_score']} | {values['pass_rate']} |")
    md.extend(["",report["leakage"]["interpretation"],"","## Извлечение",f"150 ограниченных синтетических шаблонов, field checks={report['extraction']['field_checks']}, accuracy={report['extraction']['accuracy_on_templates']}; отрицательные как required={report['extraction']['negative_as_required_errors']}; неверные offsets={report['extraction']['source_span_errors']}. Независимый human holdout: NOT_MEASURED.","","## Ограничения","","- Labels синтетические и программные, общий автор данных и продукта. Они не называются human gold.","- На профессиональных грейдах и людях пороги70/50/60 и difficulty labels ещё не валидированы.","- Параметризация не защищает от знания полного метода, полного банка или внешнего помощника.","- CPU TF-IDF вычисляет lexical similarity; глубокая семантика и найм не измерены.","- Нагрузочные API, Windows runner и browser E2E проверяются отдельным интеграционным аудитом.","","Воспроизведение: `python -m evaluation.run --seeds 100`; результаты JSON содержат bootstrap интервалы, версии и окружение."])
    (ROOT/"evaluation"/"reports"/"latest.md").write_text("\n".join(md)+"\n",encoding="utf-8",newline="\n")
    print(json.dumps({"assessment":{key:report["assessment"][key] for key in ("forms","items_checked","distinct_families_exercised","failures","seconds")},"matching":report["matching"]["baselines"],"gate_violations":report["matching"]["gate_violations"],"extraction":report["extraction"]},ensure_ascii=False,indent=2))
    if report["assessment"]["failures"] or report["round2"]["failures"]:raise SystemExit(1)


if __name__=="__main__":main()

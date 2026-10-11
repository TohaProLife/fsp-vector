"""Predeclared adverse cases and fresh assessment seeds, without human claims."""

import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime,timedelta,timezone
from copy import deepcopy
from app.engines.assessment import create_form,public_form,grade_form,need_blueprint
from app.engines.matching import admission,rank_candidates,candidate_fit_actions
from app.engines.extraction import extract_need
from app.engines.taxonomy import SPECIALIZATIONS,GRADES
from evaluation.reference_solvers import reference_answer

ROOT=Path(__file__).resolve().parents[1]
ASSESSMENT_HOLDOUT_START=400_003
NOW=datetime(2026,10,7,tzinfo=timezone.utc)
BROWSER_NEED="Ищем Middle frontend-разработчика для редактора. UI state и Web security обязательны. JavaScript concepts и Доступность будут плюсом. Удалённо,180–240тысячрублей."

EXTRACTION_CASES=[
    ("Не требуются Python, SQL и Docker.",set(),set(),{"Python","SQL","Docker"}),
    ("Python обязателен и SQL не требуется.",{"Python"},set(),{"SQL"}),
    ("SQL не нужен, Python обязателен.",{"Python"},set(),{"SQL"}),
    ("Желательны React, TypeScript и SQL.",set(),{"React","TypeScript","SQL"},set()),
    ("Не только Python, но и SQL обязателен.",{"Python","SQL"},set(),set()),
    ("SQL обязателен; PostgreSQL будет плюсом.",{"SQL"},{"PostgreSQL"},set()),
    ("Docker не требуется. Kubernetes обязателен.",{"Kubernetes"},set(),{"Docker"}),
    ("Python не обязателен, SQL обязателен.",{"SQL"},{"Python"},set()),
    ("API обязателен. API не требуется.",{"API"},set(),{"API"}),
    ("REST API нужен, Redis желателен.",{"API"},{"Redis"},set()),
    (BROWSER_NEED,{"UI state","Web security"},{"JavaScript concepts","Доступность"},set()),
    ("Python, SQL и Docker будут плюсом.",set(),{"Python","SQL","Docker"},set()),
    ("Python обязателен и SQL, Docker не требуются.",{"Python"},set(),{"SQL","Docker"}),
    ("UI state нужен, Web security не требуется.",{"UI state"},set(),{"Web security"}),
]
EXTRACTION_ROLE_CASES=[
    (BROWSER_NEED,"frontend","middle"),
    ("Frontend. CTF будет плюсом.","frontend",None),
    ("Backend. Безопасность данных обязательна.","backend",None),
    ("Frontend. Web security обязательна. Ещё ищем Senior Security engineer.",None,"senior"),
]


def round2_evaluation():
    failures=[];forms=0;items=0;blocked=0;generic_blocked=0;variations=defaultdict(set)
    for spec in SPECIALIZATIONS:
        for grade in GRADES:
            for seed in range(ASSESSMENT_HOLDOUT_START,ASSESSMENT_HOLDOUT_START+20):
                form=create_form(spec,grade,seed=seed);public=public_form(form)
                answers={item["id"]:reference_answer(item) for item in public["items"]}
                result=grade_form(form,answers);forms+=1;items+=12
                if result["score"]!=100 or not result["passed"]:failures.append({"kind":"fresh_seed_reference","spec":spec,"grade":grade,"seed":seed})
                for private in form["items"]:
                    if private.get("advanced"):
                        variations[private["family_id"]].add(json.dumps(answers[private["id"]],sort_keys=True,ensure_ascii=False))
                        withheld={key:value for key,value in answers.items() if key!=private["id"]}
                        blocked+=1
                        if grade_form(form,withheld)["passed"]:failures.append({"kind":"advanced_floor_bypass","spec":spec,"grade":grade,"seed":seed})
                if grade in ("middle","senior"):
                    withheld={item["id"]:answers[item["id"]] for item in form["items"] if not item.get("advanced")}
                    generic_blocked+=1
                    if grade_form(form,withheld)["passed"]:failures.append({"kind":"generic_shortcut_pass","spec":spec,"grade":grade,"seed":seed})
    extraction=[]
    for text,required,preferred,excluded in EXTRACTION_CASES:
        result=extract_need(text)
        ok=set(result["required_skills"])==required and set(result["preferred_skills"])==preferred and set(result["excluded_skills"])==excluded
        offsets=all(row["quote"]==text[row["start"]:row["end"]] for row in result["source_spans"])
        extraction.append({"text":text,"required":sorted(required),"preferred":sorted(preferred),"excluded":sorted(excluded),"passed":ok and offsets})
        if not ok or not offsets:failures.append({"kind":"adverse_extraction","text":text})
    roles=[]
    for text,specialization,grade in EXTRACTION_ROLE_CASES:
        result=extract_need(text)
        ok=result["specialization"]==specialization and result["grade"]==grade and result["requires_confirmation"]
        offsets=all(row["quote"]==text[row["start"]:row["end"]] for row in result["source_spans"])
        # Unsupported compact salary syntax and absent employment remain
        # unknown; improving skill extraction must not silently fill them.
        unknown_preserved=text!=BROWSER_NEED or all(result[key] is None for key in ("salary_from","salary_to","employment"))
        roles.append({"text":text,"specialization":specialization,"grade":grade,"requires_confirmation":True,"unknown_preserved":unknown_preserved,"passed":ok and offsets and unknown_preserved})
        if not roles[-1]["passed"]:failures.append({"kind":"adverse_extraction_role","text":text})
    exposure_checks=0
    for spec in SPECIALIZATIONS:
        for grade in GRADES:
            exposure={};by_comp=defaultdict(set)
            for seed in range(12):
                form=create_form(spec,grade,seed=seed,exposure=exposure)
                for item in form["items"]:
                    if item["slot"]!="short":continue
                    family=item["family_id"];exposure[family]=exposure.get(family,0)+1;by_comp[item["competency"]].add(family)
                    if seed==1 and len(by_comp[item["competency"]])!=2:failures.append({"kind":"concept_exposure_repeat_before_pool_exhaustion","spec":spec,"grade":grade})
                    exposure_checks+=1
            if max(exposure.values())-min(exposure.values())>1:failures.append({"kind":"concept_exposure_imbalance","spec":spec,"grade":grade})
    mappings=[]
    for text in ("Backend Middle. Обязательны SQL и API. Python будет плюсом.","Data analyst Senior. SQL и статистика обязательны. pandas желателен.","Frontend Junior. a11y обязателен. React желателен."):
        mappings.append(need_blueprint({"description":text}))
    need={"specialization":"backend","grade":"senior","required_skills":["SQL"],"skills":[f"nice-{i}" for i in range(20)],"work_format":"remote"}
    candidate={"id":"adverse","published":True,"specialization":"backend","confirmed_grade":"senior","score":100,"preferences":{"work_format":"remote"},"evidence":[{"skill":"SQL","source":"ASSESSMENT_VERIFIED","score":50},{"skill":"SQL","source":"PRACTICE_OBSERVED","score":100,"objectively_graded":True,"scope":{"specialization":"backend"},"confirmed_at":NOW.isoformat()},*[{"skill":skill,"source":"ASSESSMENT_VERIFIED","score":100} for skill in need["skills"]]],"assessment_at":(NOW-timedelta(days=365)).isoformat()}
    row=rank_candidates(need,[candidate],NOW)[0]
    matching_checks=[row["breakdown"]["competencies"]["value"]==.75,row["freshness"]["practice_bonus"]==.25]
    for source in ("PRACTICE_OBSERVED","NEED_PRACTICE_OBSERVED","EMPLOYER_REVIEW"):
        changed=deepcopy(candidate);changed["evidence"][0]["source"]=source
        matching_checks.append(not admission(need,changed)["eligible"])
    before=deepcopy(candidate);advice=candidate_fit_actions(need,candidate,NOW)
    matching_checks.append(candidate==before and all(item["claim"]=="conditional" for item in advice["actions"]))
    if not all(matching_checks):failures.append({"kind":"adverse_matching_or_advice"})
    artifact={"origin":"PROJECT_TEAM_AUTHORED_PROGRAMMATIC_ADVERSE_CASES","human_labelers":0,"assessment_holdout_seed_start":ASSESSMENT_HOLDOUT_START,"extraction_cases":extraction,"extraction_role_cases":roles,"need_blueprint_examples":mappings,"matching_adversarial_expected":{"weakest_required_coverage_cap":.75,"practice_max_bonus_points":1.25,"practice_must_have_admission":False},"limitation":"New seeds and independent public data solvers; no human grade calibration, response-time fairness or real vacancy-language generalization measurement."}
    (ROOT/"data"/"evaluation").mkdir(parents=True,exist_ok=True)
    (ROOT/"data"/"evaluation"/"round2-cases.json").write_text(json.dumps(artifact,ensure_ascii=False,indent=2)+"\n",encoding="utf-8",newline="\n")
    return {"status":"PASS" if not failures else "FAIL","assessment_fresh_seed_forms":forms,"assessment_fresh_seed_items":items,"one_advanced_topic_missing_blocks_pass":blocked,"generic_only_shortcut_blocks_pass":generic_blocked,"advanced_family_distinct_correct_answers":{key:len(value) for key,value in sorted(variations.items())},"concept_exposure_observations":exposure_checks,"concept_exposure_rule":"least_seen_within_compatible_two_scenario_pool; data_family_exposure_not_rotated","adverse_extraction_cases":len(extraction),"adverse_extraction_passed":sum(row["passed"] for row in extraction),"adverse_extraction_role_cases":len(roles),"adverse_extraction_role_passed":sum(row["passed"] for row in roles),"need_description_examples":len(mappings),"adverse_matching_checks":len(matching_checks),"adverse_matching_passed":sum(matching_checks),"failures":failures,"human_grade_validity":"NOT_MEASURED","parallel_form_equivalence_on_people":"NOT_MEASURED","fairness_on_response_time":"NOT_MEASURED"}

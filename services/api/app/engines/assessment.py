"""Versioned assessment DTO boundary, deterministic oracle and grade policy."""

import json
import math
import random
import secrets
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

from .bank import BANK_VERSION, build_items, family_manifest
from .safe_sql import canonical_rows, execute_select
from .taxonomy import COMPETENCY_LABELS, COMPETENCY_SKILLS, GRADES, GRADE_LABELS, SKILL_ALIASES, SPECIALIZATIONS, canonical_skill, normalize_grade, normalize_specialization

BLUEPRINT_VERSION = "vector-blueprint-2-advanced-floor"
RUBRIC_VERSION = "vector-rubric-70-50-60-v2-advanced"
TOOLS_POLICY = "docs_allowed_ai_disallowed_self_attested"
PUBLIC_ITEM_FIELDS = {"id","title","prompt","type","competency","competency_label","options","starter_code","public_cases","max_score","slot","family_version","difficulty_grade","evidence_skills","advanced"}
PUBLIC_CONTEXT_FIELDS={"context_version","scope","need_snapshot_sha256","specialization","grade","category_change","item_count","required_skills","requested_skills","tested_skills","unmeasured_skills","blueprint_rule","limitations","source","vacancy_id","invitation_id"}


def _public_context(context):
    result={key:deepcopy(value) for key,value in context.items() if key in PUBLIC_CONTEXT_FIELDS}
    for field,allowed in (("competencies",{"id","label","priority","requested_skills","measurable_skills","item_count"}),("tested_slices",{"skill","scope","certifies_global_grade"})):
        if field in context:result[field]=[{key:deepcopy(value) for key,value in row.items() if key in allowed} for row in context[field]]
    return result


def catalog() -> dict:
    entries = []
    for spec, info in SPECIALIZATIONS.items():
        allowed=allowed_contexts(spec)
        aliases={alias:target for alias,target in SKILL_ALIASES.items() if target in allowed}
        aliases.update({value:value for value in allowed})
        if "API" in allowed: aliases["REST API"]="API"
        entries.append({"id": spec, "label": info["label"], "grades": list(GRADES), "competencies": [{"id": value,"label": COMPETENCY_LABELS[value]} for value in info["competencies"]], "stacks": info["stacks"],"allowed_contexts":allowed,"default_contexts":[canonical_skill(part) for part in info["stacks"][0].split("/")],"context_aliases":aliases, "available": True, "calibration_status": "expert_initial", "limitations": "Авторская начальная рубрика. Сопоставимость и соответствие профессиональным грейдам ещё не измерены на людях."})
    return {"specializations": entries, "grades": [{"id": grade,"label": GRADE_LABELS[grade]} for grade in GRADES], "duration_minutes": 40, "item_count": 12, "blueprint_version": BLUEPRINT_VERSION, "bank_version": BANK_VERSION, "rubric_version": RUBRIC_VERSION, "policy": assessment_policy(), "family_count": len(family_manifest())}


def assessment_policy(grade=None) -> dict:
    return {"pass_score": 70,"competency_minimum": 50,"practice_minimum": 60,"advanced_minimum":75 if grade=="senior" else 60 if grade=="middle" else None,"advanced_competency_minimum":50 if grade in ("middle","senior") else None,"advanced_minimum_by_grade":{"middle":60,"senior":75},"strong_pass_score": 85,"grade_change_days": 90,"same_grade_retest_days": 7,"failed_retest_hours": 24,"duration_minutes": 40,"tools": TOOLS_POLICY,"user_code_execution": "unavailable_without_isolated_runner","practical_mode": "bounded_sql_and_declarative_data","calibration_status": "expert_initial","human_pilot": "NOT_MEASURED","ai_proctoring": "NOT_AVAILABLE","notice": "Можно пользоваться документацией; помощь AI не разрешена в этом режиме и подтверждается самим участником. Технически исключить внешнюю помощь нельзя. Middle/Senior дополнительно требуют результата по каждой сложной практической теме. Проверяются только темы и действия данного blueprint."}


def allowed_contexts(specialization: str) -> list[str]:
    """Canonical atomic route context, not an expanded certification claim."""
    from .seed import STACKS
    info=SPECIALIZATIONS[specialization]
    values=list(STACKS[specialization])
    values.extend(part.strip() for descriptor in info["stacks"] for part in descriptor.split("/"))
    values.extend(skill for comp in info["competencies"] for skill in COMPETENCY_SKILLS[comp])
    return sorted({canonical_skill(value) for value in values},key=str.casefold)


def create_form(specialization: str, grade: str, stack=None, seed=None,exposure=None) -> dict:
    specialization = normalize_specialization(specialization)
    grade = normalize_grade(grade)
    if specialization not in SPECIALIZATIONS:
        raise ValueError("Это направление пока не поддерживается банком.")
    if grade not in GRADES:
        raise ValueError("Lead и Architect не присваиваются коротким экзаменом. Выберите Intern–Senior.")
    if isinstance(seed,bool):
        raise ValueError("Invalid assessment seed")
    supplied=list(stack) if isinstance(stack,(list,tuple)) else [stack] if stack else []
    accepted={value.casefold() for value in allowed_contexts(specialization)}
    descriptors={" ".join(value.split()).casefold() for value in SPECIALIZATIONS[specialization]["stacks"]}
    normalized=[];unsupported=[]
    for raw in supplied:
        requested=" ".join(str(raw).split())
        parts=requested.split("/") if requested.casefold() in descriptors else [requested]
        for part in parts:
            context=canonical_skill(part)
            if context.casefold() not in accepted: unsupported.append(raw)
            elif context not in normalized: normalized.append(context)
    if unsupported:
        raise ValueError("Банк не поддерживает выбранный контекст: "+", ".join(map(str,unsupported)))
    private_seed = int(seed) if seed is not None else secrets.randbits(128)
    rng = random.Random(private_seed)
    if exposure is not None and (not isinstance(exposure,dict) or len(exposure)>1000 or any(not isinstance(value,int) or isinstance(value,bool) or value<0 for value in exposure.values())):
        raise ValueError("Invalid trusted exposure history")
    items = build_items(specialization,grade,rng,exposure)
    tested=sorted({skill for item in items for skill in item.get("evidence_skills",[])})
    return {"blueprint_version": BLUEPRINT_VERSION,"bank_version": BANK_VERSION,"rubric_version": RUBRIC_VERSION,"specialization": specialization,"grade": grade,"stack":supplied,"requested_stack":supplied,"context_stack":normalized,"tested_skills":tested,"unmeasured_requested_skills":[skill for skill in normalized if skill not in tested],"route":"safe_sql_declarative_concepts","duration_minutes": 40,"policy": assessment_policy(grade),"items": items,"_private": {"seed": str(private_seed),"generated_at": datetime.now(timezone.utc).isoformat()},"calibration_status": "expert_initial"}


def public_form(form: dict) -> dict:
    """Allowlist, not blacklist: future private metadata cannot accidentally leak."""
    result = {key: deepcopy(form[key]) for key in ("blueprint_version","bank_version","rubric_version","specialization","grade","stack","requested_stack","context_stack","tested_skills","unmeasured_requested_skills","route","duration_minutes","policy","calibration_status","context") if key in form}
    result["items"] = [{key: deepcopy(value) for key,value in item.items() if key in PUBLIC_ITEM_FIELDS} for item in form.get("items",[])]
    if "context" in result:result["context"]=_public_context(result["context"])
    return result


def generate_assessment(specialization, grade, stack=None, seed=None,exposure=None) -> dict:
    private = create_form(specialization,grade,stack,seed,exposure)
    result = public_form(private)
    result["private_payload"] = private
    return result


def _utf8_length(value: str) -> int:
    try:
        return len(value.encode("utf-8"))
    except UnicodeEncodeError:
        # JSON can carry an unpaired surrogate; it is an invalid answer, not a
        # grading crash that prevents all valid answers from being submitted.
        return 16_001


def _parse_json_answer(answer: Any):
    if isinstance(answer,str):
        if _utf8_length(answer) > 16_000:
            return None
        try:
            answer=json.loads(answer)
        except (ValueError,TypeError,RecursionError):
            return None
    pending=[(answer,0)];nodes=0;text_bytes=0
    while pending:
        value,depth=pending.pop();nodes+=1
        if nodes>1000 or depth>20: return None
        if isinstance(value,dict):
            if any(not isinstance(key,str) or len(key)>256 for key in value):return None
            text_bytes+=sum(_utf8_length(key) for key in value)
            pending.extend((item,depth+1) for item in value.values())
        elif isinstance(value,list): pending.extend((item,depth+1) for item in value)
        elif isinstance(value,str):text_bytes+=_utf8_length(value)
        elif isinstance(value,int) and not isinstance(value,bool) and value.bit_length()>16384:return None
        elif value is not None and not isinstance(value,(int,float,bool)):return None
        if text_bytes>16000:return None
    return answer


def _exact_equal(actual, expected) -> bool:
    # Python True == 1; JSON true must never pass a numeric answer.
    if type(actual) is not type(expected):
        if isinstance(actual,(int,float)) and not isinstance(actual,bool) and isinstance(expected,(int,float)) and not isinstance(expected,bool):
            try:return math.isfinite(float(actual)) and math.isclose(float(actual),float(expected),abs_tol=1e-6,rel_tol=0)
            except (OverflowError,ValueError):return False
        return False
    if isinstance(expected,dict):
        return set(actual) == set(expected) and all(_exact_equal(actual[key],value) for key,value in expected.items())
    if isinstance(expected,list):
        return len(actual) == len(expected) and all(_exact_equal(a,b) for a,b in zip(actual,expected))
    return actual == expected


def _grade_item(item: dict, answer: Any) -> tuple[float,str]:
    oracle = item["_oracle"]
    kind = oracle["kind"]
    if answer is None or answer == "":
        return 0., "missing"
    if kind == "choice":
        actual = answer.get("id",answer.get("value")) if isinstance(answer,dict) else answer
        return (1., "correct") if actual == oracle["expected"] else (0.,"incorrect")
    if kind == "number":
        if isinstance(answer,dict):
            answer = answer.get("value")
        if isinstance(answer,bool):
            return 0.,"invalid"
        try:
            actual = float(str(answer).strip().replace(",","."))
        except (ValueError,TypeError):
            return 0.,"invalid"
        correct = math.isfinite(actual) and abs(actual-float(oracle["expected"])) <= oracle.get("tolerance",1e-9)
        return (1.,"correct") if correct else (0.,"incorrect")
    if kind == "json":
        actual = _parse_json_answer(answer)
        return (1.,"correct") if _exact_equal(actual,oracle["expected"]) else (0.,"incorrect")
    if kind == "rubric_json":
        actual = _parse_json_answer(answer)
        expected = oracle["expected"]
        if not isinstance(actual,dict) or set(actual)-set(expected): return 0.,"invalid"
        correct={key:_exact_equal(actual.get(key),value) and key in actual for key,value in expected.items()}
        fraction=sum(correct.values())/len(expected)
        if any(not correct[key] for key in oracle.get("critical",[])): fraction=min(.4,fraction)
        return fraction,"correct" if fraction==1 else "partial" if fraction>0 else "incorrect"
    if kind == "set":
        actual = _parse_json_answer(answer)
        if not isinstance(actual,list) or any(isinstance(value,(dict,list,bool)) for value in actual):
            return 0.,"invalid"
        try:
            # Duplicate expected case IDs are invalid, so guessing a repeated list
            # cannot masquerade as a covered set of scenarios.
            correct = len(actual) == len(set(actual)) and set(actual) == set(oracle["expected"])
        except (TypeError,ValueError):
            correct = False
        return (1.,"correct") if correct else (0.,"incorrect")
    if kind == "sql":
        query = answer.get("query") if isinstance(answer,dict) else answer
        output = execute_select(query,oracle["dataset"])
        if not output["ok"]:
            return 0.,"sql_rejected"
        correct = canonical_rows(output["rows"]) == canonical_rows(oracle["rows"])
        return (1.,"correct") if correct else (0.,"incorrect")
    raise ValueError("Unsupported trusted oracle kind")


def grade_form(form: dict, answers: dict) -> dict:
    if not isinstance(answers,dict):
        raise ValueError("Answers must be keyed by item ID")
    if not form.get("items") or len(form["items"]) != 12:
        raise ValueError("Invalid private assessment form")
    allowed_ids = {item["id"] for item in form["items"]}
    if set(answers) - allowed_ids:
        raise ValueError("Answers contain unknown item IDs")
    totals = {}; skill_totals={}; advanced_totals={}; practice_points = 0.; practice_possible = 0.; points = 0.; possible = 0.; feedback = []
    for item in form["items"]:
        fraction, status = _grade_item(item,answers.get(item["id"]))
        maximum = float(item["max_score"])
        points += fraction * maximum; possible += maximum
        competency = item["competency"]
        row = totals.setdefault(competency,{"points":0.,"possible":0.,"items":0})
        row["points"] += fraction*maximum; row["possible"] += maximum; row["items"] += 1
        if item.get("advanced"):
            advanced=advanced_totals.setdefault(competency,{"points":0.,"possible":0.})
            advanced["points"]+=fraction*maximum;advanced["possible"]+=maximum
        for skill in item.get("evidence_skills",[]):
            measured=skill_totals.setdefault(skill,{"points":0.,"possible":0.,"items":0,"competency":competency})
            measured["points"]+=fraction*maximum; measured["possible"]+=maximum; measured["items"]+=1
        if item["slot"] in ("practice","mutation"):
            practice_points += fraction*maximum; practice_possible += maximum
        feedback.append({"item_id": item["id"],"competency": competency,"slot": item["slot"],"earned_score": round(fraction*maximum,2),"max_score": maximum,"status": status,"message": "Проверка выполнена корректно." if status == "correct" else "Обратите внимание на ограничения условия и граничные случаи." if status != "missing" else "Ответ не сохранён."})
    competencies = {key: round(value["points"]/value["possible"]*100,2) for key,value in totals.items()}
    score = round(points/possible*100,2)
    practice_score = round(practice_points/practice_possible*100,2)
    # The policy stored with the attempt is authoritative. An already issued v1
    # form keeps its original rubric after a deployment; new floors are not retroactive.
    policy=form.get("policy") or {"pass_score":70,"competency_minimum":50,"practice_minimum":60}
    advanced_scores={key:round(row["points"]/row["possible"]*100,2) for key,row in advanced_totals.items()}
    advanced_score=round(sum(row["points"] for row in advanced_totals.values())/sum(row["possible"] for row in advanced_totals.values())*100,2) if advanced_totals else None
    failed_floors=[]
    if score < policy.get("pass_score",70):failed_floors.append("overall")
    if min(competencies.values()) < policy.get("competency_minimum",50):failed_floors.append("competency")
    if practice_score < policy.get("practice_minimum",60):failed_floors.append("practice")
    if policy.get("advanced_minimum") is not None and (advanced_score is None or advanced_score < policy["advanced_minimum"]):failed_floors.append("advanced_overall")
    if policy.get("advanced_competency_minimum") is not None and (len(advanced_scores)!=len(competencies) or min(advanced_scores.values(),default=0)<policy["advanced_competency_minimum"]):failed_floors.append("advanced_competency")
    passed = not failed_floors
    context=_public_context(form.get("context") or {})
    need_practice=context.get("scope")=="employer_need_practice"
    evidence_source="NEED_PRACTICE_OBSERVED" if need_practice else "ASSESSMENT_VERIFIED"
    verified_skills=[]
    if passed:
        for skill,row in sorted(skill_totals.items()):
            skill_score=round(row["points"]/row["possible"]*100,2)
            if skill_score>=50 and row["items"]>=2:
                verified_skills.append({"skill":skill,"competency":row["competency"],"score":skill_score,"strength":round(skill_score/100,4),"item_count":row["items"],"source":evidence_source,"scope":{"specialization":form["specialization"],"grade":form["grade"],"mode":"safe_sql_declarative_concepts","grading":"objective","context":context.get("scope","formal_assessment"),"need_snapshot_sha256":context.get("need_snapshot_sha256"),"blueprint_version":form["blueprint_version"]}})
    return {"score": score,"passed": passed,"decision": "STRONG_PASS" if passed and score >= policy.get("strong_pass_score",85) and practice_score >= 75 else "PASS" if passed else "FAIL","competencies": competencies,"competency_details": [{"id": key,"label": COMPETENCY_LABELS[key],"score": value,"item_count": totals[key]["items"]} for key,value in competencies.items()],"practice_score": practice_score,"advanced_score":advanced_score,"advanced_competencies":advanced_scores,"failed_floors":failed_floors,"confirmed_grade": form["grade"] if passed and not need_practice else None,"category_change_allowed":passed and not need_practice,"evidence_source":evidence_source,"context":context,"verified_skills": verified_skills,"calibration_status": "expert_initial","blueprint_version": form["blueprint_version"],"rubric_version": form["rubric_version"],"bank_version": form["bank_version"],"feedback": feedback,"limitations": ["Оценка по авторской начальной рубрике; соответствие рыночным грейдам и сопоставимость форм на людях ещё не измерены.","Практика включает ограниченный SQL и декларативные проверки данных; реализация произвольного кода не оценивается.","Контроль внешней помощи не гарантируется; режим инструментов self-attested.","Практика потребности работодателя не присваивает глобальную категорию." if need_practice else "Неуспех этой попытки не отменяет ранее подтверждённую категорию."],"evidence_scope": {"specialization": form["specialization"],"competencies": list(competencies),"tools_policy": TOOLS_POLICY,"practical_mode": "bounded_sql_and_declarative_data"}}


def grade_assessment(private_payload: dict, answers: dict) -> dict:
    return grade_form(private_payload,answers)


def grade_challenge(private_rubric: dict, answer: Any) -> dict:
    """A practice observation only; never assigns a global confirmed grade."""
    item=private_rubric.get("item",private_rubric)
    if not isinstance(item,dict) or "_oracle" not in item:
        return {"status":"pending_review","score":None,"passed":None,"category_change":False,"feedback":"Практика ожидает проверки работодателем; автоматической рубрики нет."}
    fraction,status=_grade_item(item,answer)
    return {"status":"graded","score":round(fraction*100,2),"passed":fraction==1.,"category_change":False,"competency":item.get("competency"),"objective":True,"grading":"objective","tested_skills":item.get("evidence_skills",[]),"feedback":"Декларативная проверка выполнена корректно." if fraction==1. else "Сверьте ограничения условия и граничные случаи.","evidence_source":"PRACTICE_OBSERVED","calibration_status":"author_initial","limitations":"Короткая практика по конкретной теме не подтверждает грейд."}


def _utc(value) -> datetime | None:
    if isinstance(value,datetime):
        parsed = value
    elif value:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z","+00:00"))
        except ValueError:
            return None
    else:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def cooldown_policy(history: list, specialization: str, grade: str, now=None) -> dict:
    now = _utc(now) or datetime.now(timezone.utc)
    spec = normalize_specialization(specialization); grade = normalize_grade(grade)
    records = []
    for raw in history:
        context=raw.get("context") or {}
        if normalize_specialization(raw.get("specialization","")) != spec or raw.get("demo") or raw.get("scope")=="employer_need_practice" or context.get("scope")=="employer_need_practice" or raw.get("status") in ("technical_error","cancelled","running","in_progress"):
            continue
        timestamp = _utc(raw.get("finished_at") or raw.get("submitted_at"))
        if timestamp:
            records.append({**raw,"_time":timestamp,"grade":normalize_grade(raw.get("grade",""))})
    records.sort(key=lambda record:record["_time"])
    current = None; last_change = None
    for record in records:
        if record.get("passed"):
            if current != record["grade"]:
                current = record["grade"]; last_change = record["_time"]
    constraints = []
    if current is not None and current != grade and last_change is not None:
        constraints.append((last_change+timedelta(days=90),"grade_change_90_days"))
    if current == grade:
        successes = [record for record in records if record.get("passed") and record["grade"] == grade]
        if successes:
            constraints.append((successes[-1]["_time"]+timedelta(days=7),"same_grade_retest_7_days"))
    failures = [record for record in records if not record.get("passed") and record["grade"] == grade]
    if failures:
        constraints.append((failures[-1]["_time"]+timedelta(hours=24),"failed_retest_24_hours"))
    if constraints:
        date,reason = max(constraints)
        if date > now:
            return {"allowed": False,"next_allowed_at": date.isoformat(),"reason": reason,"confirmed_grade": current,"policy_version": RUBRIC_VERSION}
    return {"allowed": True,"next_allowed_at": None,"reason": "available","confirmed_grade": current,"policy_version": RUBRIC_VERSION}


# Stable imports for the API; access checks belong to the API, not this pure map.
from .need_context import need_blueprint, build_need_blueprint, generate_need_assessment

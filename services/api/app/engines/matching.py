"""Explainable evidence-first matching, never a probability of hiring."""

import math
import re
from datetime import datetime, timezone
from .taxonomy import GRADES,canonical_skill, normalize_grade, normalize_specialization

ALGORITHM_VERSION = "vector-match-v4-55-20-10-5-5-5-fsp-validity-formal-company-semantic-neutral"
WEIGHTS = {"competencies":55,"assessment":20,"preferences":10,"freshness":5,"semantic":5,"fsp":5}
PRACTICE_SOURCES = {"PRACTICE_OBSERVED","NEED_PRACTICE_OBSERVED"}
ALLOWED_EVIDENCE = {"ASSESSMENT_VERIFIED",*PRACTICE_SOURCES}
ACTIVE_EVIDENCE_STATES = {"active", "verified"}
FSP_SOURCES = {"FSP_DEMO_CONFIRMED","FSP_REGISTRY_VERIFIED"}


def _active_evidence(raw):
    # Unknown, blank and future states must not silently acquire verified status.
    # Missing status retains compatibility with old, trusted active records.
    allowed=ACTIVE_EVIDENCE_STATES | {"observed"} if raw.get("source") in PRACTICE_SOURCES else ACTIVE_EVIDENCE_STATES
    return not raw.get("revoked") and str(raw.get("status", "active")).strip().lower() in allowed


def _synthetic_evidence(raw):
    scope=raw.get("scope")
    return raw.get("origin")=="SYNTHETIC_SEED" or raw.get("calibration_status")=="synthetic_fixture" or isinstance(scope,dict) and scope.get("mode")=="synthetic_fixture"


def _event_key(achievement):
    for field in ("event_id", "protocol_id"):
        value = achievement.get(field)
        if value:
            return (field, str(value)) if isinstance(value, (str, int)) and not isinstance(value, bool) else None
    # Legacy trusted fixtures may lack an explicit registry event ID.
    fields = tuple(achievement.get(field) for field in ("title", "date", "place", "discipline"))
    return ("legacy", fields) if all(value is None or isinstance(value, (str, int, float, bool)) for value in fields) else None


def _positive_integer(value):
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
        if isinstance(value, float) and (not math.isfinite(value) or value != number):
            return None
        if isinstance(value, str) and not re.fullmatch(r"[0-9]+", value.strip()):
            return None
        return number if number > 0 else None
    except (ValueError, TypeError, OverflowError):
        return None


def _unit(value, fallback=0.):
    if isinstance(value,bool):return fallback
    try:
        value = float(value)
        if not math.isfinite(value): return fallback
        return min(1.,max(0.,value))
    except (ValueError,TypeError,OverflowError):
        return fallback


def _score_unit(value):
    if isinstance(value,bool):return 0.
    try:return _unit(float(value)/100)
    except (ValueError,TypeError,OverflowError):return 0.


def _time(value):
    if isinstance(value,datetime):
        parsed=value
    elif value:
        try: parsed=datetime.fromisoformat(str(value).replace("Z","+00:00"))
        except ValueError: return None
    else: return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def _skills(value):
    if isinstance(value,str): value=[part.strip() for part in value.split(",") if part.strip()]
    result=[]
    for entry in value or []:
        skill=entry.get("skill",entry.get("name","")) if isinstance(entry,dict) else entry
        if skill:
            skill=canonical_skill(skill)
            if skill not in result: result.append(skill)
    return result


def _company_scope_allows(raw,company_id):
    scope=raw.get("scope")
    scoped_company=scope.get("company_id") if isinstance(scope,dict) else None
    if raw.get("source")=="NEED_PRACTICE_OBSERVED":
        return bool(company_id and scoped_company and str(company_id)==str(scoped_company))
    if scoped_company:
        return bool(company_id and str(company_id)==str(scoped_company))
    return True


def evidence_map(candidate:dict,specialization:str,sources=None,company_id=None) -> dict:
    result={}
    for raw in candidate.get("evidence",[]) or []:
        if not isinstance(raw,dict) or raw.get("source") not in (sources or ALLOWED_EVIDENCE):
            continue
        if not _company_scope_allows(raw,company_id):continue
        if not _active_evidence(raw):
            continue
        scope=raw.get("scope")
        synthetic=_synthetic_evidence(raw)
        if raw.get("source")=="ASSESSMENT_VERIFIED" and (raw.get("is_demo") and not synthetic or isinstance(scope,dict) and scope.get("global_grade") is False):
            continue
        scoped_spec=scope.get("specialization") if isinstance(scope,dict) else scope
        if scoped_spec and normalize_specialization(scoped_spec) != specialization:
            continue
        scoped_grade=scope.get("grade") if isinstance(scope,dict) else None
        if raw.get("source")=="ASSESSMENT_VERIFIED" and scoped_grade and normalize_grade(scoped_grade)!=normalize_grade(candidate.get("confirmed_grade") or (candidate.get("category") or {}).get("grade", "")):
            continue
        if raw.get("source") in PRACTICE_SOURCES and not (raw.get("objectively_graded") is True or isinstance(scope,dict) and scope.get("grading")=="objective"):
            continue
        skill=canonical_skill(raw.get("skill",""))
        if not skill: continue
        strength=_unit(raw.get("strength")) if raw.get("strength") is not None else _score_unit(raw.get("score"))
        # A short employer practice cannot stand in for a whole formal exam.
        if raw.get("source") in PRACTICE_SOURCES: strength=min(.6,strength)
        if skill not in result or strength>result[skill]["strength"]:
            result[skill]={"strength":strength,"source":raw["source"],"confirmed_at":raw.get("confirmed_at"),"scope":scope,"synthetic":synthetic}
    return result


def preference_fit(need,candidate):
    preferences=candidate.get("preferences") or {}
    checks=[]; hard=[]
    offered_format=need.get("work_format")
    preferred_format=preferences.get("work_format")
    compatible_format=_compatible_preference(offered_format,preferred_format)
    if preferred_format or offered_format: checks.append(float(compatible_format))
    if not compatible_format and preferences.get("strict_work_format",True): hard.append("work_format")
    offered_employment=need.get("employment")
    preferred_employment=preferences.get("employment")
    compatible_employment=_compatible_preference(offered_employment,preferred_employment)
    if offered_employment or preferred_employment: checks.append(float(compatible_employment))
    if not compatible_employment and preferences.get("strict_employment",False): hard.append("employment")
    n_from,n_to=need.get("salary_from"),need.get("salary_to")
    c_from,c_to=preferences.get("salary_from"),preferences.get("salary_to")
    if any(value is not None for value in (n_from,n_to,c_from,c_to)):
        compatible_salary=not (n_to is not None and c_from is not None and float(n_to)<float(c_from) or c_to is not None and n_from is not None and float(n_from)>float(c_to))
        checks.append(float(compatible_salary))
        if not compatible_salary and preferences.get("strict_salary",True): hard.append("salary")
    return (sum(checks)/len(checks) if checks else .5),hard


def _compatible_preference(offered,preferred):
    # "Any" means the party accepts each supported concrete option, symmetrically.
    # Missing information retains the existing non-excluding/neutral policy.
    if not offered or not preferred:return True
    offered=" ".join(str(offered).split()).casefold()
    preferred=" ".join(str(preferred).split()).casefold()
    return offered in ("any","любой") or preferred in ("any","любой") or offered==preferred


def required_minimum(need):
    """An explicit employer floor may strengthen the baseline, never weaken it."""
    return max(.5,_unit(need.get("required_min_strength"),.5))


def admission(need,candidate,company_id=None):
    company_id=company_id or need.get("company_id")
    reasons=[]
    spec=normalize_specialization(need.get("specialization",""))
    candidate_spec=normalize_specialization(candidate.get("specialization",""))
    raw_grade=candidate.get("confirmed_grade")
    if not raw_grade and isinstance(candidate.get("category"),dict): raw_grade=candidate["category"].get("grade")
    grade=normalize_grade(raw_grade or "")
    if not candidate.get("published",False): reasons.append("profile_private")
    if not candidate.get("active",True) or candidate.get("status") in ("blocked","deleted","suspended"): reasons.append("account_inactive")
    if grade not in GRADES: reasons.append("category_unconfirmed")
    if spec and candidate_spec != spec: reasons.append("specialization_mismatch")
    requested=need.get("grades") or ([need.get("grade")] if need.get("grade") else [])
    if requested and grade not in [normalize_grade(value) for value in requested]: reasons.append("grade_mismatch")
    if company_id and company_id in (candidate.get("blocked_companies") or []): reasons.append("company_blocked")
    _,hard=preference_fit(need,candidate)
    reasons.extend(f"preference_{value}" for value in hard)
    evidence=evidence_map(candidate,candidate_spec,company_id=company_id)
    formal=evidence_map(candidate,candidate_spec,{"ASSESSMENT_VERIFIED"},company_id)
    required=_skills(need.get("required_skills"))
    # Explicit training mode can admit unknown skills; reasons still expose them.
    if need.get("require_verified_skills",True) and need.get("must_have_mode","verified") != "training_allowed":
        if any(formal.get(skill,{}).get("strength",0)<required_minimum(need) for skill in required): reasons.append("required_evidence_missing")
    return {"eligible": not reasons,"reasons": reasons,"evidence": evidence,"formal_evidence":formal,"required_min_strength":required_minimum(need),"confirmed_grade": grade}


def freshness_signal(need,candidate,now,company_id=None):
    company_id=company_id or need.get("company_id")
    observed=_time(candidate.get("assessment_at"))
    age=(now-observed).total_seconds()/86400 if observed else None
    base=max(0.,1-age/365) if age is not None and age>=0 else 0.
    relevant=set(_skills(need.get("required_skills"))+_skills(need.get("skills")))
    spec=normalize_specialization(candidate.get("specialization", ""))
    bonus=0.;measurements=[]
    for raw in candidate.get("evidence",[]) or []:
        if not isinstance(raw,dict) or raw.get("source") not in PRACTICE_SOURCES:continue
        if not _company_scope_allows(raw,company_id):continue
        scope=raw.get("scope")
        if not isinstance(scope,dict) or normalize_specialization(scope.get("specialization",""))!=spec:continue
        if not (raw.get("objectively_graded") is True or scope.get("grading")=="objective"):continue
        if not _active_evidence(raw):continue
        skill=canonical_skill(raw.get("skill",""))
        score=raw.get("score")
        if skill not in relevant or isinstance(score,bool) or not isinstance(score,(int,float)) or not math.isfinite(score) or not 60<=score<=100:continue
        stamp=_time(raw.get("confirmed_at"))
        elapsed=(now-stamp).total_seconds()/86400 if stamp else None
        if elapsed is None or not 0<=elapsed<90:continue
        amount=.25*(1-elapsed/90)
        if amount>bonus:bonus=amount
        measurements.append({"skill":skill,"source":raw["source"],"age_days":round(elapsed,2),"score":score})
    return {"value":min(1.,base+bonus),"formal_base":round(base,4),"practice_bonus":round(min(1.,base+bonus)-base,4),"maximum_practice_bonus_points":1.25,"observations":measurements,"policy":"objective_relevant_90_days_max_bonus_1_25_points"}


def fsp_signal(candidate,specialization,now):
    fsp=candidate.get("fsp") or {}
    if not isinstance(fsp,dict): return 0.,[]
    status=str(fsp.get("status","not_linked")).strip().lower()
    source=fsp.get("source",fsp.get("provenance"))
    if status not in ("sync_ok","linked","verified","verified_demo","linked_no_history") or source not in FSP_SOURCES:
        return 0.,[]
    achievements=fsp.get("achievements") or []
    if not isinstance(achievements,list):return 0.,[]
    # Revocation dominates an older active duplicate, regardless of input order.
    revoked_events={_event_key(row) for row in achievements if isinstance(row,dict) and not _active_evidence(row)}
    signals=[]; explain=[]; seen_events=set()
    for achievement in achievements:
        if not isinstance(achievement,dict):continue
        event_key=_event_key(achievement)
        if event_key is None or event_key in revoked_events:continue
        if event_key in seen_events: continue
        if not _active_evidence(achievement) or achievement.get("source",source)!=source:continue
        scopes=achievement.get("specializations") or []
        discipline=str(achievement.get("discipline","")).lower()
        scope_relevant=specialization in [normalize_specialization(value) for value in scopes]
        discipline_relevant=(specialization=="security" and any(word in discipline for word in ("ctf","information security","информационная безопасность"))) or (specialization in ("backend","data","qa") and any(word in discipline for word in ("алгоритм","algorithm")))
        relevant=scope_relevant or discipline_relevant
        # Official QA B1: every valid discipline has the same sporting base;
        # role context can add at most .2 and never excludes another discipline.
        context_coefficient=.8+.2*int(relevant)
        place=_positive_integer(achievement.get("place")); participants=_positive_integer(achievement.get("participants",achievement.get("participants_count")))
        if place is None or participants is None or participants<place:continue
        relative=1-(place-1)/participants
        date=_time(achievement.get("date"))
        if date is None or date>now:continue
        age=(now-date).total_seconds()/86400
        freshness=max(.1,1-age/1095)
        team_factor=.5 if achievement.get("team") and not achievement.get("role") else 1.
        signal=relative*freshness*team_factor*context_coefficient
        seen_events.add(event_key)
        signals.append(signal)
        explain.append({"event":achievement.get("title",achievement.get("event_name","Достижение ФСП")),"source":source,"relative_result":round(relative,3),"team_role_known":bool(achievement.get("role")),"is_demo":source=="FSP_DEMO_CONFIRMED" or bool(fsp.get("is_demo") or achievement.get("is_demo")),"sport_base_coefficient":.8,"context_bonus_coefficient":.2 if relevant else 0.,"context_coefficient":context_coefficient,"relevance_basis":"verified_specialization_scope" if scope_relevant else "discipline_role_map" if discipline_relevant else "equal_sport_base","policy_status":"author_initial_context_weight"})
    signals.sort(reverse=True)
    total=0.
    for value in signals: total += (1-total)*value*.6
    return min(1.,total),explain


def rank_candidates(need:dict,candidates:list,now=None,company_id=None,**kwargs) -> list:
    now=_time(now) or datetime.now(timezone.utc)
    result=[]
    required=_skills(need.get("required_skills")); desired=[skill for skill in _skills(need.get("skills")) if skill not in required]
    requirements=[(skill,2.) for skill in required]+[(skill,1.) for skill in desired]
    candidates=[candidate for candidate in candidates if admission(need,candidate,company_id or need.get("company_id"))["eligible"]]
    semantic_enabled=bool(kwargs.get("semantic_enabled",need.get("semantic_enabled",False)))
    model=None
    if semantic_enabled and candidates:
        from .semantic import candidate_text,fit_index
        model=fit_index(tuple(candidate_text(candidate) for candidate in candidates))
    for candidate_index,candidate in enumerate(candidates):
        gate=admission(need,candidate,company_id or need.get("company_id"))
        if not gate["eligible"]: continue
        spec=normalize_specialization(candidate.get("specialization","")); evidence=gate["evidence"]
        coverage=sum(weight*(gate["formal_evidence"] if skill in required else evidence).get(skill,{}).get("strength",0.) for skill,weight in requirements)/sum(weight for _,weight in requirements) if requirements else .5
        weakest_required=min((gate["formal_evidence"].get(skill,{}).get("strength",0.) for skill in required),default=None)
        raw_coverage=coverage
        if weakest_required is not None:coverage=min(coverage,weakest_required+.25)
        test_score=_score_unit(candidate.get("score",candidate.get("assessment_score",0)))
        p,_=preference_fit(need,candidate)
        freshness_detail=freshness_signal(need,candidate,now,company_id)
        freshness=freshness_detail["value"]
        fsp,fsp_reasons=fsp_signal(candidate,spec,now)
        semantic={"value":.5,"status":"disabled_neutral_constant","model_version":None,"artifact_sha256":None,"confidence":"not_applicable"}
        if model is not None:
            from .semantic import need_text
            semantic=model.similarity(need_text(need),candidate_index)
        features={"competencies":coverage,"assessment":test_score,"preferences":p,"freshness":freshness,"semantic":semantic["value"],"fsp":fsp}
        breakdown={key:{"value":round(value,4),"weight":WEIGHTS[key],"points":round(value*WEIGHTS[key],2)} for key,value in features.items()}
        breakdown["fsp"].update(sport_base_coefficient=.8,context_bonus_maximum=.2,discipline_policy="equal_base_optional_role_relevance",policy_status="author_initial_context_weight")
        score=round(sum(value*WEIGHTS[key] for key,value in features.items()),2)
        declared=set(_skills(candidate.get("skills")))
        verified=[skill for skill,_ in requirements if gate["formal_evidence"].get(skill,{}).get("strength",0)>=required_minimum(need) if skill in required] + [skill for skill,_ in requirements if skill not in required and gate["formal_evidence"].get(skill,{}).get("strength",0)>=.5]
        observed_skills=[skill for skill,_ in requirements if skill not in verified and evidence.get(skill,{}).get("source") in PRACTICE_SOURCES and evidence[skill]["strength"]>0]
        gaps=[{"skill":skill,"required":skill in required,"state":"practice_observed_no_formal" if skill in observed_skills else "self_declared_unverified" if skill in declared else "unknown","message":"Есть ограниченная практика; формальный экзамен по навыку не подтверждён" if skill in observed_skills else "Заявлен, но не проверен" if skill in declared else "Не измерялся"} for skill,_ in requirements if skill not in verified]
        formal=gate["formal_evidence"]
        synthetic_category=all(row["synthetic"] for row in formal.values()) if formal else candidate.get("source")=="synthetic_fixture" or candidate.get("category_source")=="SYNTHETIC_SEED"
        category_text=f"Синтетическая категория {spec} × {gate['confirmed_grade']}; реальный участник этот экзамен не проходил." if synthetic_category else f"Категория {spec} × {gate['confirmed_grade']} подтверждена; область измерения ограничена экзаменом."
        reasons=[{"kind":"category","text":category_text,"source_kind":"synthetic_fixture" if synthetic_category else "formal_assessment"}]
        if verified:
            measured=[skill for skill in verified if not formal[skill]["synthetic"]]
            fixtures=[skill for skill in verified if formal[skill]["synthetic"]]
            evidence_text=" · ".join((["Проверены экзаменом: "+", ".join(measured)] if measured else [])+(["Синтетические примеры навыков: "+", ".join(fixtures)] if fixtures else []))
            reasons.append({"kind":"evidence","text":evidence_text,"skills":verified,"sources":{skill:formal[skill]["source"] for skill in verified},"source_kinds":{skill:"synthetic_fixture" if formal[skill]["synthetic"] else "formal_assessment" for skill in verified}})
        if raw_coverage>coverage:reasons.append({"kind":"weakest_required","text":"Слабый обязательный навык ограничивает вклад общих компетенций; дополнительные навыки не устраняют этот пробел.","weakest_strength":round(weakest_required,4),"unlimited_coverage":round(raw_coverage,4),"limited_coverage":round(coverage,4)})
        if freshness_detail["practice_bonus"]:reasons.append({"kind":"practice_freshness","text":"Свежая объективная практика по требованиям добавляет ограниченный сигнал актуальности, сохраняя категорию.","points":round(freshness_detail["practice_bonus"]*5,2)})
        reasons.append({"kind":"preferences","text":"Условия предложения совместимы с опубликованными предпочтениями." if p==1 else "Условия известны частично или есть допустимые расхождения; уточните их до приглашения."})
        if fsp_reasons: reasons.append({"kind":"fsp","text":f"{'Демонстрационный' if any(row['is_demo'] for row in fsp_reasons) else 'Подтверждённый'} сигнал ФСП: +{round(fsp*5,2):g} пункта; одинаковая спортивная база 0,8 для всех дисциплин и до 0,2 за контекст направления, не заменяет категорию.","achievements":fsp_reasons})
        algorithm_version=ALGORITHM_VERSION.replace("semantic-neutral","cpu-tfidf") if semantic_enabled else ALGORITHM_VERSION
        result.append({"candidate_id":str(candidate.get("id",candidate.get("candidate_id",""))),"score":score,"breakdown":breakdown,"reasons":reasons,"gaps":gaps,"verified_skills":verified,"observed_skills":observed_skills,"required_min_strength":gate["required_min_strength"],"weakest_required_strength":weakest_required,"freshness":freshness_detail,"algorithm_version":algorithm_version,"score_kind":"compatibility_index","semantic_status":semantic["status"],"semantic":semantic})
    return sorted(result,key=lambda item:(-item["score"],item["candidate_id"]))


def explain_exclusion(need,candidate,company_id=None):
    result=admission(need,candidate,company_id)
    return {"eligible":result["eligible"],"reasons":result["reasons"]}


def candidate_fit_actions(need,candidate,now=None,company_id=None):
    """Private candidate advice. Hypothetical actions never mutate evidence/gates.

    No invented exam result or promised future ranking delta. Only an achievable
    preference-only delta is calculated, with all existing gates still applied.
    The API must expose this only to the candidate owning the profile/context.
    """
    from copy import deepcopy
    gate=admission(need,candidate,company_id)
    ranked=rank_candidates(need,[candidate],now,company_id)
    current=ranked[0]["score"] if ranked else None
    actions=[]
    if "profile_private" in gate["reasons"]:actions.append({"kind":"publication_consent","message":"Для участия в подборе нужна публикация профиля с вашим согласием.","claim":"conditional","estimated_delta":None})
    for reason in gate["reasons"]:
        if reason.startswith("preference_"):actions.append({"kind":"negotiate_conditions","field":reason.removeprefix("preference_"),"message":"Согласуйте совместимые условия предложения, сохраняя ваши реальные предпочтения.","claim":"conditional","estimated_delta":None})
        elif reason in ("category_unconfirmed","grade_mismatch","specialization_mismatch"):
            actions.append({"kind":"formal_assessment_or_compatible_need","message":"Выберите потребность вашей подтверждённой категории или пройдите допустимый формальный экзамен. Практика работодателя категорию не меняет.","claim":"conditional","estimated_delta":None})
    for skill in _skills(need.get("required_skills")):
        observed=gate["formal_evidence"].get(skill,{})
        if observed.get("strength",0)<required_minimum(need):
            from .taxonomy import COMPETENCY_SKILLS,SPECIALIZATIONS
            spec=normalize_specialization(need.get("specialization",""))
            supported=skill in {value for comp in SPECIALIZATIONS.get(spec,{}).get("competencies",[]) for value in COMPETENCY_SKILLS[comp]}
            actions.append({"kind":"formal_skill_evidence" if supported else "unmeasured_requirement","skill":skill,"current_strength":observed.get("strength"),"minimum_strength":required_minimum(need),"evidence_required":"ASSESSMENT_VERIFIED","bank_supported":supported,"message":"Подтвердите навык формальным экзаменом в подходящей категории." if supported else "Текущий банк не проверяет этот навык. Нужен дополнительный метод проверки или явно согласованный обучающий режим потребности.","claim":"conditional","estimated_delta":None})
    if gate["eligible"]:
        preferences=candidate.get("preferences") or {}
        for field in ("work_format","employment"):
            offered=need.get(field)
            if not offered or str(offered).casefold() in ("any","любой") or _compatible_preference(offered,preferences.get(field)):continue
            hypothetical=deepcopy(candidate)
            hypothetical.setdefault("preferences",{})[field]=offered
            changed=rank_candidates(need,[hypothetical],now,company_id)
            if changed and changed[0]["score"]>current:
                actions.append({"kind":"preference_compatibility","field":field,"proposed_value":offered,"estimated_delta":round(changed[0]["score"]-current,2),"message":"Если этот формат действительно подходит вам, уточнение предпочтения изменит только сигнал условий. Подтверждение навыков останется прежним.","claim":"conditional"})
        if not freshness_signal(need,candidate,_time(now) or datetime.now(timezone.utc),company_id)["practice_bonus"]:
            actions.append({"kind":"objective_relevant_practice","maximum_delta":1.25,"estimated_delta":None,"message":"Объективная короткая практика по требованиям может добавить до 1.25 пункта актуальности. Она не заменит обязательное формальное подтверждение.","claim":"conditional"})
    return {"algorithm_version":ALGORITHM_VERSION,"current_fit":{"eligible":gate["eligible"],"score":current},"blockers":gate["reasons"],"actions":actions,"limitations":["Это условные рекомендации, не прогноз найма и не обещание результата экзамена.","Ни hard gates, ни профиль, ни доказательства не изменяются этим расчётом."]}

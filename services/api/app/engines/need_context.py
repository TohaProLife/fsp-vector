"""Authorized snapshot → transparent fixed-blueprint practice mapping.

The API owns access checks. A context never turns employer text into an oracle,
changes global grade thresholds, or certifies an unmeasured framework/language.
"""

import hashlib
import json
from copy import deepcopy
from .taxonomy import COMPETENCY_LABELS, COMPETENCY_SKILLS, GRADES, SPECIALIZATIONS, canonical_skill, normalize_grade, normalize_specialization
from .extraction import extract_need

CONTEXT_VERSION="vector-need-context-1"
SNAPSHOT_FIELDS=("id","company_id","title","description","specialization","grade","skills","required_skills","salary_from","salary_to","work_format","employment")


def _snapshot(need):
    if not isinstance(need,dict):raise ValueError("Потребность должна быть объектом.")
    snapshot={key:deepcopy(need[key]) for key in SNAPSHOT_FIELDS if key in need}
    for key in ("title","description"):
        value=snapshot.get(key,"")
        if not isinstance(value,str) or len(value)>20000:raise ValueError("Текст потребности должен быть строкой до 20 000 символов.")
    for key in ("skills","required_skills"):
        value=snapshot.get(key,[])
        if not isinstance(value,list) or len(value)>60 or any(not isinstance(skill,str) or len(skill)>100 for skill in value):raise ValueError("Навыки потребности должны быть списком до 60 коротких строк.")
    try:serialized=json.dumps(snapshot,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False)
    except (TypeError,ValueError,RecursionError) as error:raise ValueError("Некорректный snapshot потребности.") from error
    if len(serialized.encode("utf-8"))>90000:raise ValueError("Потребность превышает допустимый размер.")
    return snapshot,hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def need_blueprint(need):
    snapshot,digest=_snapshot(need)
    extracted=extract_need(snapshot.get("title","")+"\n"+snapshot.get("description",""))
    spec=normalize_specialization(snapshot.get("specialization") or extracted.get("specialization") or "")
    grade=normalize_grade(snapshot.get("grade") or extracted.get("grade") or "")
    if spec not in SPECIALIZATIONS or grade not in GRADES:raise ValueError("Для практики нужно явно выбрать одно поддерживаемое направление и грейд Intern–Senior.")
    # Structured reviewed requirements prevail over text extraction. Empty arrays
    # are explicit too: we do not re-add a skill an employer deliberately removed.
    required=snapshot.get("required_skills",extracted["required_skills"])
    requested=snapshot.get("skills",extracted["skills"])
    required=list(dict.fromkeys(canonical_skill(skill) for skill in required))
    requested=list(dict.fromkeys(required+[canonical_skill(skill) for skill in requested]))
    measured=[skill for comp in SPECIALIZATIONS[spec]["competencies"] for skill in COMPETENCY_SKILLS[comp]]
    rows=[]
    for comp in SPECIALIZATIONS[spec]["competencies"]:
        covered=[skill for skill in requested if skill in COMPETENCY_SKILLS[comp]]
        rows.append({"id":comp,"label":COMPETENCY_LABELS[comp],"priority":"required" if any(skill in required for skill in covered) else "preferred" if covered else "common_blueprint","requested_skills":covered,"measurable_skills":COMPETENCY_SKILLS[comp],"item_count":3})
    tested=[skill for skill in requested if skill in measured]
    unmeasured=[skill for skill in requested if skill not in measured]
    return {"context_version":CONTEXT_VERSION,"scope":"employer_need_practice","need_snapshot_sha256":digest,"specialization":spec,"grade":grade,"category_change":False,"item_count":12,"competencies":rows,"required_skills":required,"requested_skills":requested,"tested_skills":tested,"unmeasured_skills":unmeasured,"tested_slices":[{"skill":skill,"scope":"bounded_data_and_concepts","certifies_global_grade":False} for skill in tested],"blueprint_rule":"fixed_common_blueprint_no_hidden_employer_weights","limitations":["Это практика по прозрачной карте требований, а не отдельный глобальный экзамен.","Проверяются только точные навыки банка; Python, React, Docker и другие реализации не выводятся из концептуальных задач.","Неизмеренные обязательные навыки останутся неизмеренными и не получат ASSESSMENT_VERIFIED.","Веса и пороги общего blueprint сохранены. Соответствие грейдам на людях не измерено."]}


build_need_blueprint=need_blueprint


def generate_need_assessment(need,seed=None,exposure=None):
    from .assessment import create_form,public_form
    context=need_blueprint(need)
    snapshot,_=_snapshot(need)
    private=create_form(context["specialization"],context["grade"],seed=seed,exposure=exposure)
    private["context"]=context
    private["scope"]="employer_need_practice"
    private["_private"]["need_snapshot"]=snapshot
    # Rotate blocks by need priority, never change scores or difficulty. A formal
    # twelve-item common blueprint remains comparable at the structural level.
    priority={row["id"]:{"required":0,"preferred":1,"common_blueprint":2}[row["priority"]] for row in context["competencies"]}
    private["items"].sort(key=lambda item:priority[item["competency"]])
    public=public_form(private)
    public.update(scope="employer_need_practice",category_change=False,private_payload=private)
    return public

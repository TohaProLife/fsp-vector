import json
import secrets
from copy import deepcopy
from collections import Counter
from datetime import timedelta
from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from .auth import CandidateUser
from .assessment_review import review_submission
from .common import DB, audit, aware, candidate_for, company_processing_active, emit, iso, lock_candidate, processing_active, require
from .models import AssessmentAttempt, Candidate, Company, CompanyBlock, Invitation, Need, Vacancy, utcnow

router = APIRouter(prefix="/assessments", tags=["Assessment & category"])


def engine_catalog():
    from .engines.assessment import catalog
    result = catalog()
    result.setdefault("duration_minutes", 40)
    result.setdefault("item_count", 12)
    result["judge_available"] = False
    result["execution_policy"] = "safe_declarative_only; arbitrary_code_fail_closed"
    return result


def policy_for(db, candidate, specialization, grade):
    from .engines.assessment import cooldown_policy
    history = []
    for row in db.scalars(select(AssessmentAttempt).where(AssessmentAttempt.candidate_id == candidate.id)):
        if row.private_form.get("scope", "global_category") != "global_category":
            continue
        history.append({"specialization": row.specialization, "grade": row.grade, "status": row.status,
            "demo": row.demo, "started_at": iso(row.started_at), "finished_at": iso(row.finished_at),
            "passed": row.result.get("passed", False) if row.result else False,
            "score": row.result.get("score") if row.result else None})
    return cooldown_policy(history, specialization, grade)


def attempt_dto(db, row, candidate):
    if row.status == "in_progress" and aware(row.expires_at) <= utcnow():
        row.status, row.finished_at = "expired", row.expires_at
        db.flush()
    form = row.private_form
    # Only whitelisted public items were stored alongside the private payload.
    result = {"id": row.id, "status": row.status, "specialization": row.specialization,
        "grade": row.grade, "stack": row.stack, "demo": row.demo, "expires_at": iso(row.expires_at),
        "started_at": iso(row.started_at), "items": form["items"], "answers": row.answers,
        "result": row.result, "policy": form.get("policy", {}),
        "blueprint_version": form.get("blueprint_version"),
        "calibration_status": form.get("calibration_status", "expert_initial")}
    result.update({key: form.get(key) for key in ("tested_skills", "unmeasured_requested_skills", "route")})
    result.update({"scope": form.get("scope", "global_category"), "context": form.get("context"),
                   "certifies_global_category": form.get("scope", "global_category") == "global_category" and not row.demo})
    return result


@router.get("/catalog")
def catalog():
    return engine_catalog()


@router.get("/availability")
def availability(account: CandidateUser, db: DB, specialization: str | None = None):
    candidate = candidate_for(db, account)
    specialization = specialization or candidate.specialization or "backend"
    taxonomy = engine_catalog()
    require(specialization in {item["id"] for item in taxonomy["specializations"]}, detail="Выберите доступную специализацию.")
    active = db.scalar(select(AssessmentAttempt).where(AssessmentAttempt.candidate_id == candidate.id,
        AssessmentAttempt.status == "in_progress", AssessmentAttempt.expires_at > utcnow()))
    return {"specialization": specialization,
            "items": [{"grade": grade["id"], **policy_for(db, candidate, specialization, grade["id"])} for grade in taxonomy["grades"]],
            "active_attempt": {"id": active.id, "specialization": active.specialization, "grade": active.grade,
                "scope": active.private_form.get("scope", "global_category"), "expires_at": iso(active.expires_at)} if active else None,
            "server_time": iso(utcnow())}


class Start(BaseModel):
    specialization: str = Field(max_length=40)
    grade: str = Field(max_length=20)
    stack: list[str] = Field(default_factory=list, max_length=20)
    demo: bool = False


@router.post("/start", status_code=201)
def start(data: Start, account: CandidateUser, db: DB):
    from .engines.assessment import generate_assessment
    candidate = candidate_for(db, account)
    candidate = db.scalar(select(Candidate).where(Candidate.id == candidate.id).execution_options(populate_existing=True).with_for_update())
    require(processing_active(db,candidate),403,"PROCESSING_CONSENT_REQUIRED","Согласие на обработку было отозвано.")
    require(candidate.survey, 409, "SURVEY_REQUIRED", "Сначала пройдите обязательный опрос.")
    require(candidate.survey.get("specialization") == data.specialization and candidate.survey.get("grade") == data.grade,
            409, "SURVEY_MISMATCH", "Обновите опрос для выбранной специализации и грейда.")
    active = db.scalar(select(AssessmentAttempt).where(AssessmentAttempt.candidate_id == candidate.id,
                       AssessmentAttempt.status == "in_progress").with_for_update())
    if active and aware(active.expires_at) > utcnow():
        require(active.specialization == data.specialization and active.grade == data.grade and active.demo == data.demo,
                409, "ATTEMPT_ACTIVE", "Завершите текущую попытку, прежде чем начать другую.")
        require(active.private_form.get("scope", "global_category") == "global_category", 409,
                "ATTEMPT_ACTIVE", "Завершите текущую практику, прежде чем начать экзамен.")
        return attempt_dto(db, active, candidate)
    if active:
        active.status, active.finished_at = "expired", active.expires_at
    policy = policy_for(db, candidate, data.specialization, data.grade)
    require(data.demo or policy.get("allowed", False), 409, "ASSESSMENT_COOLDOWN",
            f"Новая попытка пока недоступна: {policy.get('reason', '')}. Дата: {policy.get('next_allowed_at', '—')}")
    stack = data.stack or candidate.survey.get("stack", [])
    exposure = Counter()
    prior_forms = db.scalars(select(AssessmentAttempt.private_form).where(AssessmentAttempt.candidate_id == candidate.id)).all()
    for prior in prior_forms:
        for item in prior.get("private_payload", {}).get("items", []):
            if item.get("family_id"):
                exposure[item["family_id"]] += 1
    try:
        form = generate_assessment(data.specialization, data.grade, stack=stack, seed=secrets.randbits(62),exposure=dict(exposure))
    except ValueError as exc:
        require(False, 422, "ASSESSMENT_ROUTE_UNAVAILABLE", str(exc))
    require(form.get("items") and form.get("private_payload"), 503, "ASSESSMENT_UNAVAILABLE", "Не найден полноценный банк для выбранного маршрута.")
    row = AssessmentAttempt(candidate_id=candidate.id, specialization=data.specialization, grade=data.grade,
                            stack=stack, demo=data.demo, private_form=form,
                            expires_at=utcnow() + timedelta(minutes=form.get("duration_minutes", 40)))
    db.add(row)
    db.flush()
    audit(db, account, "assessment.started", row.id, {"demo": data.demo, "blueprint": form.get("blueprint_version")})
    return attempt_dto(db, row, candidate)


class NeedStart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    invitation_id: str | None = Field(default=None, max_length=100)
    vacancy_id: str | None = Field(default=None, max_length=100)


def accessible_need_context(db, candidate, data):
    require(bool(data.invitation_id) != bool(data.vacancy_id), detail="Выберите ровно одно приглашение или вакансию.")
    if data.invitation_id:
        from .hiring import effective_status
        invitation = db.scalar(select(Invitation).where(Invitation.id == data.invitation_id,
            Invitation.candidate_id == candidate.id).with_for_update())
        require(invitation is not None and effective_status(invitation) in {"pending", "accepted"},
                404, "NOT_FOUND", "Приглашение недоступно для практики.")
        snapshot = invitation.data.get("need_snapshot")
        if snapshot is None and invitation.need_id:
            need = db.get(Need, invitation.need_id)
            snapshot = need.data if need and need.company_id == invitation.company_id else None
        if snapshot is None and invitation.vacancy_id:
            vacancy = db.get(Vacancy, invitation.vacancy_id)
            snapshot = vacancy.data if vacancy and vacancy.company_id == invitation.company_id else None
        require(snapshot is not None, 409, "NEED_CONTEXT_REQUIRED", "У приглашения нет структурированной потребности. Выберите вакансию.")
        context = {"type": "invitation", "id": invitation.id, "company_id": invitation.company_id,
                   "need_id": invitation.need_id}
    else:
        vacancy = db.scalar(select(Vacancy).where(Vacancy.id == data.vacancy_id, Vacancy.published.is_(True)).with_for_update())
        require(vacancy is not None, 404, "NOT_FOUND", "Вакансия снята с публикации.")
        snapshot = vacancy.data
        context = {"type": "vacancy", "id": vacancy.id, "company_id": vacancy.company_id}
    require(not db.scalar(select(CompanyBlock).where(CompanyBlock.company_id == context["company_id"],
        CompanyBlock.candidate_id == candidate.id)), 404, "NOT_FOUND", "Практика этой компании недоступна.")
    require(company_processing_active(db, db.get(Company, context["company_id"]), lock=True),
            409, "COMPANY_UNAVAILABLE", "Практика временно недоступна: работодатель должен подтвердить email и согласие на обработку.")
    return deepcopy(snapshot), context


@router.post("/need-start", status_code=201)
def start_need(data: NeedStart, account: CandidateUser, db: DB):
    from .engines.assessment import generate_need_assessment
    candidate = lock_candidate(db, account)
    snapshot, access_context = accessible_need_context(db, candidate, data)
    active = db.scalar(select(AssessmentAttempt).where(AssessmentAttempt.candidate_id == candidate.id,
        AssessmentAttempt.status == "in_progress").with_for_update())
    if active and aware(active.expires_at) > utcnow():
        require(active.private_form.get("scope") == "employer_need_practice" and
                active.private_form.get("context", {}).get("access_context") == access_context,
                409, "ATTEMPT_ACTIVE", "Завершите текущую попытку, прежде чем начать другую.")
        return attempt_dto(db, active, candidate)
    if active:
        active.status, active.finished_at = "expired", active.expires_at
    previous = db.scalars(select(AssessmentAttempt).where(AssessmentAttempt.candidate_id == candidate.id)
        .order_by(AssessmentAttempt.started_at.desc())).all()
    exposure = Counter()
    for prior in previous:
        for item in prior.private_form.get("private_payload", {}).get("items", []):
            if item.get("family_id"):
                exposure[item["family_id"]] += 1
    prior_context = next((prior for prior in previous if prior.private_form.get("scope") == "employer_need_practice" and
        prior.private_form.get("context", {}).get("access_context") == access_context), None)
    if prior_context and prior_context.finished_at:
        retry = aware(prior_context.finished_at) + timedelta(hours=24)
        require(retry <= utcnow(), 409, "PRACTICE_COOLDOWN", f"Новая практика по этой потребности доступна {iso(retry)}.")
    try:
        form = generate_need_assessment(snapshot, seed=secrets.randbits(62), exposure=dict(exposure))
    except ValueError:
        require(False, 422, "ASSESSMENT_ROUTE_UNAVAILABLE", "Для потребности не найден допустимый маршрут практики.")
    require(form.get("items") and form.get("private_payload"), 503, "ASSESSMENT_UNAVAILABLE", "Банк практики временно недоступен.")
    form["scope"] = "employer_need_practice"
    form["context"] = {**form.get("context", {}), "access_context": access_context}
    form["private_payload"]["context"] = deepcopy(form["context"])
    row = AssessmentAttempt(candidate_id=candidate.id, specialization= snapshot["specialization"],
        grade=snapshot["grade"], stack=form.get("stack", []), demo=False, private_form=form,
        expires_at=utcnow() + timedelta(minutes=form.get("duration_minutes", 40)))
    db.add(row)
    db.flush()
    audit(db, account, "assessment.need_practice_started", row.id,
          {"source_type": access_context["type"], "source_id": access_context["id"], "category_changed": False})
    return attempt_dto(db, row, candidate)


def own_attempt(db, candidate, attempt_id, lock=False):
    query = select(AssessmentAttempt).where(AssessmentAttempt.id == attempt_id,
                                           AssessmentAttempt.candidate_id == candidate.id)
    if lock:
        query = query.execution_options(populate_existing=True).with_for_update()
    row = db.scalar(query)
    require(row is not None, 404, "NOT_FOUND", "Попытка не найдена.")
    return row


@router.get("/{attempt_id}")
def attempt(attempt_id: str, account: CandidateUser, db: DB):
    candidate = candidate_for(db, account)
    return attempt_dto(db, own_attempt(db, candidate, attempt_id, lock=True), candidate)


class Answers(BaseModel):
    answers: dict = Field(default_factory=dict)


class SubmitAnswers(Answers):
    review_token: str | None = Field(default=None, max_length=64)
    allow_incomplete: bool = False


def review_attempt(row, draft_answers):
    from .engines.assessment import public_form
    snapshot = public_form(row.private_form)
    snapshot.update({"scope": row.private_form.get("scope", "global_category"), "demo": row.demo})
    return review_submission(snapshot, row.answers, draft_answers)


def check_answers(row, values):
    from .assessment_review import _tree_issue
    issue = _tree_issue(values)
    require(issue is None, 422, "ANSWER_JSON_INVALID", "Ответы должны быть конечным JSON допустимой сложности.")
    try:
        encoded = json.dumps(values, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, OverflowError, RecursionError):
        require(False, 422, "ANSWER_JSON_INVALID", "Ответы должны быть корректным JSON без NaN, Infinity и некорректных Unicode-строк.")
    require(len(encoded) <= 100_000, 413, "ANSWERS_TOO_LARGE", "Ответы превышают допустимый размер.")
    ids = {item["id"] for item in row.private_form["items"]}
    require(set(values) <= ids, detail="В ответах есть неизвестные задания.")
    for value in values.values():
        require(isinstance(value, (str, list, dict, int, float, bool)) or value is None,
                detail="Формат ответа не поддерживается.")


@router.put("/{attempt_id}/answers")
def save_answers(attempt_id: str, data: Answers, account: CandidateUser, db: DB):
    candidate = lock_candidate(db, account)
    row = own_attempt(db, candidate, attempt_id, lock=True)
    require(row.status == "in_progress" and aware(row.expires_at) > utcnow(), 409, "ATTEMPT_CLOSED", "Время истекло или попытка уже завершена.")
    prospective = {**row.answers, **data.answers}
    check_answers(row, prospective)
    row.answers = prospective
    return {"id": row.id, "answers": row.answers, "saved_at": iso(utcnow())}


@router.post("/{attempt_id}/review")
def review(attempt_id: str, data: Answers, account: CandidateUser, db: DB):
    candidate = lock_candidate(db, account)
    row = own_attempt(db, candidate, attempt_id, lock=True)
    require(row.status == "in_progress" and aware(row.expires_at) > utcnow(), 409,
            "ATTEMPT_CLOSED", "Время истекло или попытка уже завершена.")
    return review_attempt(row, data.answers)


@router.post("/{attempt_id}/submit")
def submit(attempt_id: str, data: SubmitAnswers, account: CandidateUser, db: DB):
    from .engines.assessment import grade_assessment
    candidate = candidate_for(db, account)
    candidate = db.scalar(select(Candidate).where(Candidate.id == candidate.id).execution_options(populate_existing=True).with_for_update())
    require(processing_active(db,candidate),403,"PROCESSING_CONSENT_REQUIRED","Согласие на обработку было отозвано.")
    row = own_attempt(db, candidate, attempt_id, lock=True)
    if row.status == "completed":
        return attempt_dto(db, row, candidate)
    require(row.status == "in_progress" and aware(row.expires_at) > utcnow(), 409, "ATTEMPT_CLOSED", "Время истекло или попытка уже завершена.")
    reviewed = review_attempt(row, data.answers)
    require(not any(issue["kind"] in {"format", "limit"} for issue in reviewed["issues"]),
            422, "ASSESSMENT_ANSWER_INVALID", "Исправьте формат или размер ответов. Попытка остаётся открытой.")
    if data.review_token is not None:
        require(reviewed["review_token"] is not None and data.review_token.isascii() and
                secrets.compare_digest(data.review_token, reviewed["review_token"]),
                409, "REVIEW_STALE", "Ответы или задания изменились. Повторите проверку перед отправкой.")
        require(data.allow_incomplete or not any(issue["kind"] == "missing" for issue in reviewed["issues"]),
                422, "ASSESSMENT_INCOMPLETE", "Есть незаполненные ответы. Подтвердите сдачу с пропусками или заполните их.")
    row.answers = {**row.answers, **data.answers}
    result = grade_assessment(row.private_form["private_payload"], row.answers)
    scope = row.private_form.get("scope", "global_category")
    formal = scope == "global_category"
    result["demo"] = row.demo
    result["scope"] = scope
    result.pop("category_change", None)
    result["category_change_allowed"] = bool(formal and result.get("passed") and not row.demo)
    result["certifies_global_category"] = bool(formal and result.get("passed") and not row.demo)
    old_category = candidate.confirmed_categories.get(row.specialization)
    result["category_changed"] = bool(formal and result.get("passed") and not row.demo and
                                     (not old_category or old_category.get("grade") != row.grade))
    result["attempt_id"] = row.id
    row.status, row.finished_at, row.result = "completed", utcnow(), result
    if formal and result.get("passed") and not row.demo:
        candidate.confirmed_grade, candidate.score = row.grade, result["score"]
        candidate.specialization, candidate.assessment_at = row.specialization, row.finished_at
        candidate.confirmed_categories = {**candidate.confirmed_categories, row.specialization: {
            "grade": row.grade, "score": result["score"], "confirmed_at": iso(row.finished_at),
            "attempt_id": row.id, "calibration_status": result.get("calibration_status", "expert_initial")}}
        evidence = [e for e in candidate.evidence if not (e.get("source") == "ASSESSMENT_VERIFIED" and
                    e.get("scope", {}).get("specialization") == row.specialization)]
        for skill in result.get("verified_skills", []):
            value = skill.get("skill") if isinstance(skill, dict) else skill
            if not value:
                continue
            competency = skill.get("competency") if isinstance(skill, dict) else None
            competencies = result.get("competencies", {})
            measured = skill.get("score") if isinstance(skill, dict) else None
            if measured is None and competency and isinstance(competencies, dict):
                measured = competencies.get(competency)
                measured = measured.get("score") if isinstance(measured, dict) else measured
            # Without a skill-specific measurement, keep evidence unscored instead of
            # presenting the total exam score as proof of every individual skill.
            strength = skill.get("strength") if isinstance(skill, dict) else None
            if strength is None and measured is not None:
                strength = measured / 100
            evidence.append({"skill": value, "source": "ASSESSMENT_VERIFIED", "status": "verified",
                "strength": strength, "score": measured, "competency": competency, "confirmed_at": iso(row.finished_at),
                "attempt_id": row.id, "scope": {**(skill.get("scope", {}) if isinstance(skill,dict) else {}),
                "specialization": row.specialization, "grade": row.grade}, "requested_stack": row.stack})
        candidate.evidence = evidence
        candidate.fixture = False
    elif not formal and result.get("passed"):
        context = row.private_form.get("context", {})
        measured = []
        for skill in result.get("verified_skills", []):
            if not isinstance(skill, dict) or not skill.get("skill"):
                continue
            measured.append({"skill": skill["skill"], "source": "NEED_PRACTICE_OBSERVED", "status": "observed",
                "score": skill.get("score"), "strength": skill.get("strength"), "objectively_graded": True,
                "competency": skill.get("competency"), "attempt_id": row.id, "confirmed_at": iso(row.finished_at),
                "need_snapshot_sha256": context.get("need_snapshot_sha256"),
                "scope": {**skill.get("scope", {}), "specialization": row.specialization, "global_grade": False,
                          "company_id": context.get("access_context", {}).get("company_id")}})
        candidate.evidence = [item for item in candidate.evidence if not (item.get("source") == "NEED_PRACTICE_OBSERVED" and
            item.get("need_snapshot_sha256") == context.get("need_snapshot_sha256"))] + measured
    result["confirmed_grade"] = candidate.confirmed_grade if formal else None
    if not formal:
        result["global_confirmed_grade"] = candidate.confirmed_grade
    row.result = dict(result)
    notice_title = ("Демо-результат экзамена готов" if row.demo else
                    "Результат экзамена готов" if formal else
                    "Результат практики по потребности готов")
    emit(db, account.id, "assessment.completed", notice_title, {"attempt_id": row.id, "passed": result.get("passed"), "demo": row.demo})
    audit(db, account, "assessment.completed", row.id, {"score": result["score"], "passed": result.get("passed"), "demo": row.demo})
    return attempt_dto(db, row, candidate)

import json
from typing import Any
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field, StrictBool
from sqlalchemy import select
from .auth import CandidateUser, EmployerUser, Verified
from .common import DB, audit, aware, candidate_for, candidate_projection, company_dto, company_for, company_processing_active, emit, iso, lock_candidate, private_content_reason, processing_active, require, rows
from .employer import NeedData, validate_need
from .hiring import grant_contacts
from .models import Application, Candidate, Challenge, ChallengeSubmission, Company, CompanyBlock, Vacancy, utcnow
from .practice import challenge_visible, ensure_weekly_challenge, latest_submission, retry_at, submission_dto, week_window

router = APIRouter(tags=["Vacancies, applications & practice"])


def vacancy_dto(db, row):
    company = db.get(Company, row.company_id)
    return {"id": row.id, "company_id": row.company_id, **row.data, "company": company_dto(company),
            "published": row.published, "salary_from": row.salary_from, "salary_to": row.salary_to,
            "created_at": iso(row.created_at)}


@router.get("/vacancies")
def vacancies(account: Verified, db: DB, q: str = "", specialization: str | None = None):
    query = select(Vacancy)
    if account.role == "employer":
        query = query.where(Vacancy.company_id == company_for(db, account).id)
    else:
        query = query.where(Vacancy.published.is_(True))
    items = []
    for row in db.scalars(query.order_by(Vacancy.created_at.desc())):
        if account.role == "candidate" and not company_processing_active(db, db.get(Company, row.company_id)):
            continue
        if specialization and row.data.get("specialization") != specialization:
            continue
        if q and q.casefold() not in (row.data.get("title", "") + " " + row.data.get("description", "")).casefold():
            continue
        items.append(vacancy_dto(db, row))
    return rows(items)


class VacancyData(NeedData):
    published: bool = True


@router.post("/vacancies", status_code=201)
def create_vacancy(data: VacancyData, account: EmployerUser, db: DB):
    company = company_for(db, account)
    require(company.description.strip() and company.contact.strip(), 409, "COMPANY_PROFILE_REQUIRED", "Добавьте описание компании и контакт.")
    values = data.model_dump()
    validate_need(values)
    published = values.pop("published")
    row = Vacancy(company_id=company.id, data=values, published=published,
                  salary_from=values["salary_from"], salary_to=values["salary_to"])
    db.add(row)
    db.flush()
    audit(db, account, "vacancy.created", row.id)
    return vacancy_dto(db, row)


@router.get("/vacancies/{vacancy_id}")
def vacancy(vacancy_id: str, account: Verified, db: DB):
    row = db.get(Vacancy, vacancy_id)
    company = company_for(db, account) if account.role == "employer" else None
    require(row is not None and (row.published or company and row.company_id == company.id),
            404, "NOT_FOUND", "Вакансия не найдена.")
    if account.role == "candidate":
        require(company_processing_active(db, db.get(Company, row.company_id)), 404, "NOT_FOUND", "Вакансия временно недоступна.")
    return vacancy_dto(db, row)


@router.patch("/vacancies/{vacancy_id}")
def update_vacancy(vacancy_id: str, data: dict, account: EmployerUser, db: DB):
    company = company_for(db, account)
    row = db.get(Vacancy, vacancy_id)
    require(row is not None and row.company_id == company.id, 404, "NOT_FOUND", "Вакансия не найдена.")
    values = VacancyData.model_validate({**row.data, "published": row.published, **data}).model_dump()
    validate_need(values)
    row.published = values.pop("published")
    row.data, row.salary_from, row.salary_to = values, values["salary_from"], values["salary_to"]
    audit(db, account, "vacancy.updated", row.id)
    return vacancy_dto(db, row)


def application_dto(db, row, account):
    vacancy = db.get(Vacancy, row.vacancy_id)
    candidate = db.get(Candidate, row.candidate_id)
    company = db.get(Company, vacancy.company_id)
    privacy_reason = private_content_reason(db, candidate, company) if account.role == "employer" else None
    return {"id": row.id, "vacancy_id": row.vacancy_id, "candidate_id": row.candidate_id,
            "status": row.status, "message": "" if privacy_reason else row.message, "created_at": iso(row.created_at),
            "private_content_available": privacy_reason is None, "content_redacted": privacy_reason is not None,
            "privacy_reason": privacy_reason,
            "vacancy": vacancy_dto(db, vacancy),
            "candidate": candidate_projection(db, candidate, company, own=account.role == "candidate")}


class ApplyData(BaseModel):
    message: str = Field(default="", max_length=3000)
    # Disclosure is opt-in: an omitted checkbox/API field is not permission.
    consent_contacts: StrictBool = False


@router.post("/vacancies/{vacancy_id}/apply", status_code=201)
def apply(vacancy_id: str, data: ApplyData, account: CandidateUser, db: DB):
    candidate = candidate_for(db, account)
    candidate = db.scalar(select(Candidate).where(Candidate.id == candidate.id).execution_options(populate_existing=True).with_for_update())
    require(processing_active(db,candidate),403,"PROCESSING_CONSENT_REQUIRED","Согласие на обработку было отозвано.")
    vacancy = db.scalar(select(Vacancy).where(Vacancy.id == vacancy_id).with_for_update())
    require(vacancy is not None and vacancy.published, 404, "NOT_FOUND", "Вакансия снята с публикации.")
    company = db.get(Company, vacancy.company_id)
    require(company_processing_active(db, company, lock=True), 409, "COMPANY_UNAVAILABLE",
            "Компания временно недоступна: работодатель должен подтвердить email и согласие на обработку.")
    require(data.consent_contacts, detail="Отклик раскрывает контакты компании. Подтвердите согласие.")
    require(not db.scalar(select(CompanyBlock).where(CompanyBlock.company_id == vacancy.company_id,
                        CompanyBlock.candidate_id == candidate.id)), 403, "COMPANY_BLOCKED", "Разблокируйте компанию, прежде чем откликнуться.")
    existing = db.scalar(select(Application).where(Application.vacancy_id == vacancy.id, Application.candidate_id == candidate.id).with_for_update())
    if existing:
        return application_dto(db, existing, account)
    row = Application(vacancy_id=vacancy.id, candidate_id=candidate.id, message=data.message)
    db.add(row)
    db.flush()
    grant = grant_contacts(db, candidate.id, vacancy.company_id, source="self_application")
    emit(db, company.account_id, "application.received", "Новый отклик на вакансию", {"application_id": row.id})
    audit(db, account, "application.created", row.id, {"grant_id": grant.id})
    return application_dto(db, row, account)


@router.get("/applications")
def applications(account: Verified, db: DB):
    query = select(Application)
    if account.role == "candidate":
        query = query.where(Application.candidate_id == candidate_for(db, account).id)
    else:
        company = company_for(db, account)
        query = query.join(Vacancy).where(Vacancy.company_id == company.id)
    return rows([application_dto(db, row, account) for row in db.scalars(query.order_by(Application.created_at.desc()))])


class ApplicationStatus(BaseModel):
    status: str


@router.patch("/applications/{application_id}")
def update_application(application_id: str, data: ApplicationStatus, account: EmployerUser, db: DB):
    company = company_for(db, account)
    row = db.get(Application, application_id)
    require(row is not None and db.get(Vacancy, row.vacancy_id).company_id == company.id, 404, "NOT_FOUND", "Отклик не найден.")
    require(data.status in {"new", "review", "interview", "offer", "accepted", "rejected"}, detail="Неизвестный статус отклика.")
    candidate = db.scalar(select(Candidate).where(Candidate.id == row.candidate_id)
                          .execution_options(populate_existing=True).with_for_update())
    db.info.setdefault("processing_cache", {}).pop(candidate.id, None)
    privacy_reason = private_content_reason(db, candidate, company)
    require(privacy_reason != "processing_withdrawn", 409, "CANDIDATE_UNAVAILABLE", "Изменение остановлено: кандидат отозвал обработку данных.")
    require(privacy_reason != "company_blocked", 403, "COMPANY_BLOCKED", "Кандидат ограничил доступ этой компании.")
    row = db.scalar(select(Application).where(Application.id == application_id)
                    .execution_options(populate_existing=True).with_for_update())
    require(company_processing_active(db, company, lock=True), 409, "COMPANY_UNAVAILABLE",
            "Компания временно недоступна: работодатель должен подтвердить email и согласие на обработку.")
    row.status = data.status
    emit(db, candidate.account_id, "application.updated", "Статус отклика изменился", {"application_id": row.id, "status": row.status})
    audit(db, account, "application.updated", row.id, {"status": row.status})
    return application_dto(db, row, account)


def challenge_dto(db, row, account=None):
    company = db.get(Company, row.company_id) if row.company_id else None
    result = {"id": row.id, **row.data, "company": company_dto(company) if company else None,
              "published": row.published, "created_at": iso(row.created_at),
              "category_changes": False, "grading": row.rubric.get("kind", "manual")}
    if account and account.role == "candidate":
        candidate = candidate_for(db, account)
        submission = db.scalar(select(ChallengeSubmission).where(ChallengeSubmission.challenge_id == row.id,
                        ChallengeSubmission.candidate_id == candidate.id).order_by(ChallengeSubmission.created_at.desc()).limit(1))
        result["last_result"] = submission.result if submission else None
    return result


@router.get("/challenges")
def challenges(account: Verified, db: DB, specialization: str | None = None):
    query = select(Challenge).where(Challenge.published.is_(True))
    items = []
    candidate = candidate_for(db, account) if account.role == "candidate" else None
    for row in db.scalars(query.order_by(Challenge.created_at.desc())):
        if not challenge_visible(row, account, candidate):
            continue
        if candidate and row.company_id and not company_processing_active(db, db.get(Company, row.company_id)):
            continue
        if specialization and row.data.get("specialization") != specialization:
            continue
        items.append(challenge_dto(db, row, account))
    return rows(items)


@router.get("/challenges/weekly")
def weekly_challenge(account: CandidateUser, db: DB):
    candidate = lock_candidate(db, account)
    row = ensure_weekly_challenge(db, candidate, account)
    submission = latest_submission(db, row, candidate)
    week_id, opened, next_week = week_window()
    next_retry = retry_at(submission)
    return {"week_id": week_id, "opens_at": iso(opened), "next_week_at": iso(next_week), "timezone": "UTC",
            "challenge": challenge_dto(db, row, account), "submission": submission_dto(submission),
            "completed": bool(submission and submission.result.get("passed")),
            "retry_at": iso(next_retry) if next_retry and next_retry > utcnow() else None,
            "policy": {"recurrence": "weekly", "failed_retry_hours": 24, "category_changes": False,
                       "notifications_consent_purpose": "practice"}}


class ChallengeData(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=10, max_length=5000)
    specialization: str = Field(max_length=40)
    skill: str = Field(max_length=80)
    public_task: dict = Field(default_factory=dict)


@router.post("/challenges", status_code=201)
def create_challenge(data: ChallengeData, account: EmployerUser, db: DB):
    company = company_for(db, account)
    require(len(json.dumps(data.public_task)) <= 20000, detail="Задание слишком большое.")
    # Custom company tasks enter manual review. Their text cannot create global evidence.
    row = Challenge(company_id=company.id, data=data.model_dump(), rubric={"kind": "manual"})
    db.add(row)
    db.flush()
    audit(db, account, "challenge.created", row.id)
    return challenge_dto(db, row, account)


@router.get("/challenges/{challenge_id}")
def challenge(challenge_id: str, account: Verified, db: DB):
    row = db.get(Challenge, challenge_id)
    candidate = candidate_for(db, account) if account.role == "candidate" else None
    require(row is not None and row.published and challenge_visible(row, account, candidate), 404, "NOT_FOUND", "Задание не найдено.")
    if candidate and row.company_id:
        require(company_processing_active(db, db.get(Company, row.company_id)), 404, "NOT_FOUND", "Задание временно недоступно.")
    return challenge_dto(db, row, account)


class ChallengeAnswer(BaseModel):
    answer: Any


@router.post("/challenges/{challenge_id}/submit", status_code=201)
def submit_challenge(challenge_id: str, data: ChallengeAnswer, account: CandidateUser, db: DB):
    from .engines.assessment import grade_challenge
    from .assessment_review import _tree_issue
    row = db.get(Challenge, challenge_id)
    require(row is not None and row.published, 404, "NOT_FOUND", "Задание не найдено.")
    issue = _tree_issue(data.answer, maximum_text_bytes=30000)
    require(issue is None, 413 if issue and issue[0] == "limit" else 422,
            "ANSWER_TOO_LARGE" if issue and issue[0] == "limit" else "ANSWER_JSON_INVALID",
            "Ответ должен быть конечным JSON допустимого размера и сложности.")
    try:
        encoded = json.dumps(data.answer, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, OverflowError, RecursionError):
        require(False, 422, "ANSWER_JSON_INVALID", "Ответ должен быть корректным JSON без NaN, Infinity и некорректных Unicode-строк.")
    require(len(encoded) <= 30000, 413, "ANSWER_TOO_LARGE", "Ответ слишком большой.")
    candidate = lock_candidate(db,account)
    require(challenge_visible(row, account, candidate), 404, "NOT_FOUND", "Задание не найдено.")
    if row.company_id:
        require(company_processing_active(db, db.get(Company, row.company_id), lock=True), 409,
                "COMPANY_UNAVAILABLE", "Практика временно недоступна: работодатель должен подтвердить email и согласие на обработку.")
    if row.rubric.get("kind") != "manual":
        previous = latest_submission(db, row, candidate)
        if previous and previous.result.get("passed"):
            return {**submission_dto(previous), "replayed": True}
        next_retry = retry_at(previous)
        require(not next_retry or next_retry <= utcnow(), 409, "PRACTICE_COOLDOWN",
                f"Повтор этой задачи доступен {iso(next_retry)}. Можно выбрать другую практику.")
    if row.rubric.get("kind") == "manual":
        result = {"status": "awaiting_review", "score": None, "passed": None,
                  "feedback": "Решение сохранено. Работодатель должен проверить его вручную.", "category_changed": False}
    else:
        result = grade_challenge(row.rubric, data.answer)
        result["category_changed"] = False
    submission = ChallengeSubmission(challenge_id=row.id, candidate_id=candidate.id,
                                     answer={"value": data.answer}, result=result)
    db.add(submission)
    db.flush()
    if result.get("passed"):
        evidence = [item for item in candidate.evidence if not (item.get("source") == "PRACTICE_OBSERVED" and item.get("challenge_id") == row.id)]
        evidence.append({"skill": row.data.get("skill", "Практика"), "source": "PRACTICE_OBSERVED",
                         "status": "observed", "strength": (result.get("score") or 0) / 100,
                         "score": result.get("score"), "objectively_graded": True,
                         "confirmed_at": iso(utcnow()), "challenge_id": row.id,
                         "scope": {"specialization": row.data.get("specialization"), "global_grade": False,
                                   "mode": "bounded_sql_declarative_practice"}})
        candidate.evidence = evidence
    audit(db, account, "challenge.submitted", row.id, {"submission_id": submission.id, "status": result.get("status")})
    return {"id": submission.id, "challenge_id": row.id, "result": result, "created_at": iso(submission.created_at)}


@router.get("/challenges/{challenge_id}/submissions")
def challenge_submissions(challenge_id: str, account: EmployerUser, db: DB):
    company = company_for(db, account)
    challenge = db.get(Challenge, challenge_id)
    require(challenge is not None and challenge.company_id == company.id, 404, "NOT_FOUND", "Задание не найдено.")
    items = []
    for row in db.scalars(select(ChallengeSubmission).where(ChallengeSubmission.challenge_id == challenge.id).order_by(ChallengeSubmission.created_at.desc())):
        candidate = db.get(Candidate, row.candidate_id)
        privacy_reason = private_content_reason(db, candidate, company)
        items.append({"id": row.id, "challenge_id": row.challenge_id,
            "answer": None if privacy_reason else row.answer,
            "result": {"status": "content_unavailable", "content_redacted": True} if privacy_reason else row.result,
            "created_at": iso(row.created_at), "private_content_available": privacy_reason is None,
            "content_redacted": privacy_reason is not None, "privacy_reason": privacy_reason,
            "candidate": candidate_projection(db, candidate, company)})
    return rows(items)


class PracticeReview(BaseModel):
    score: int = Field(ge=0, le=100)
    feedback: str = Field(min_length=5, max_length=3000)


@router.post("/challenges/{challenge_id}/submissions/{submission_id}/review")
def review_practice(challenge_id: str, submission_id: str, data: PracticeReview, account: EmployerUser, db: DB):
    company = company_for(db, account)
    challenge = db.get(Challenge, challenge_id)
    require(challenge is not None and challenge.company_id == company.id, 404, "NOT_FOUND", "Задание не найдено.")
    require(challenge.rubric.get("kind") == "manual", 409, "OBJECTIVE_RUBRIC_LOCKED", "Автоматический результат нельзя заменить субъективной оценкой компании.")
    row = db.scalar(select(ChallengeSubmission).where(ChallengeSubmission.id == submission_id,
        ChallengeSubmission.challenge_id == challenge.id))
    require(row is not None, 404, "NOT_FOUND", "Решение не найдено.")
    candidate = db.scalar(select(Candidate).where(Candidate.id == row.candidate_id)
                          .execution_options(populate_existing=True).with_for_update())
    db.info.setdefault("processing_cache", {}).pop(candidate.id, None)
    privacy_reason = private_content_reason(db, candidate, company)
    require(privacy_reason != "processing_withdrawn", 409, "CANDIDATE_UNAVAILABLE", "Проверка остановлена: кандидат отозвал обработку данных.")
    require(privacy_reason != "company_blocked", 403, "COMPANY_BLOCKED", "Кандидат ограничил доступ этой компании.")
    row = db.scalar(select(ChallengeSubmission).where(ChallengeSubmission.id == submission_id)
                    .execution_options(populate_existing=True).with_for_update())
    require(company_processing_active(db, company, lock=True), 409, "COMPANY_UNAVAILABLE",
            "Проверка временно недоступна: работодатель должен подтвердить email и согласие на обработку.")
    row.result = {"status":"company_reviewed","score":data.score,"passed":data.score>=70,
        "feedback":data.feedback,"source":"COMPANY_REVIEWED","company_id":company.id,
        "reviewed_at":iso(utcnow()),"category_changed":False,
        "limitations":"Субъективная оценка компании. Не влияет на глобальный грейд и подтверждённые навыки."}
    emit(db, candidate.account_id, "challenge.reviewed", "Работодатель проверил вашу практику", {"challenge_id":challenge.id,"submission_id":row.id})
    audit(db, account, "challenge.company_reviewed", row.id, {"score":data.score,"category_changed":False})
    return {"id":row.id,"challenge_id":challenge.id,"result":row.result}

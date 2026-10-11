from datetime import datetime, timedelta
from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select
from .auth import CandidateUser, EmployerUser, Verified
from .common import DB, audit, aware, candidate_accessible, candidate_for, candidate_projection, company_dto, company_for, company_processing_active, emit, has_grant, iso, private_content_reason, processing_active, require, rows, salary_valid
from .models import Account, Candidate, Company, CompanyBlock, ContactGrant, Invitation, InvitationMessage, Need, Outbox, Report, Vacancy, utcnow

router = APIRouter(tags=["Invitations & contact grants"])


def effective_status(row):
    if row.status == "pending" and row.expires_at and aware(row.expires_at) <= utcnow():
        return "expired"
    return row.status


def invitation_dto(db, row, account):
    company = db.get(Company, row.company_id)
    candidate = db.get(Candidate, row.candidate_id)
    employer_view = account.role == "employer"
    privacy_reason = private_content_reason(db, candidate, company) if employer_view else None
    candidate_view = candidate_projection(db, candidate, company if employer_view else None, own=not employer_view)
    messages = db.scalars(select(InvitationMessage).where(InvitationMessage.invitation_id == row.id).order_by(InvitationMessage.created_at)).all()
    grant = db.scalar(select(ContactGrant).where(ContactGrant.candidate_id == candidate.id, ContactGrant.company_id == company.id))
    return {"id": row.id, "candidate_id": row.candidate_id, "company_id": row.company_id,
            "need_id": row.need_id, "vacancy_id": row.vacancy_id, **row.data,
            "salary_from": row.salary_from, "salary_to": row.salary_to,
            "status": effective_status(row), "company": row.company_snapshot,
            "viewed_at": row.data.get("viewed_at"),
            "candidate": candidate_view, "created_at": iso(row.created_at), "updated_at": iso(row.updated_at),
            "expires_at": iso(row.expires_at), "contact_grant_id": grant.id if grant else None,
            "contacts_open": bool(grant and grant.revoked_at is None and processing_active(db, candidate)
                                  and company_processing_active(db, company)),
            "private_content_available": privacy_reason is None, "content_redacted": privacy_reason is not None,
            "privacy_reason": privacy_reason,
            "messages": [{"id": message.id,
                "text": "" if privacy_reason and message.account_id != account.id else message.text,
                "content_redacted": bool(privacy_reason and message.account_id != account.id),
                "author_role": db.get(Account, message.account_id).role, "created_at": iso(message.created_at)} for message in messages]}


def owned_invitation(db, account, invitation_id, lock=False):
    query = select(Invitation).where(Invitation.id == invitation_id)
    row = db.scalar(query.execution_options(populate_existing=True).with_for_update() if lock else query)
    require(row is not None, 404, "NOT_FOUND", "Приглашение не найдено.")
    if account.role == "candidate":
        require(row.candidate_id == candidate_for(db, account).id, 404, "NOT_FOUND", "Приглашение не найдено.")
    else:
        require(row.company_id == company_for(db, account).id, 404, "NOT_FOUND", "Приглашение не найдено.")
    return row


@router.get("/invitations")
def invitations(account: Verified, db: DB):
    query = select(Invitation)
    if account.role == "candidate":
        query = query.where(Invitation.candidate_id == candidate_for(db, account).id)
    else:
        query = query.where(Invitation.company_id == company_for(db, account).id)
    return rows([invitation_dto(db, row, account) for row in db.scalars(query.order_by(Invitation.created_at.desc()))])


class InvitationData(BaseModel):
    candidate_id: str
    need_id: str | None = None
    vacancy_id: str | None = None
    title: str = Field(min_length=2, max_length=200)
    message: str = Field(min_length=10, max_length=5000)
    salary_from: int = Field(gt=0, le=10_000_000)
    salary_to: int = Field(gt=0, le=10_000_000)
    work_format: str = "remote"
    employment: str = "full_time"
    contact: str = Field(min_length=3, max_length=300)
    expires_at: datetime | None = None


@router.post("/invitations", status_code=201)
def create_invitation(data: InvitationData, account: EmployerUser, db: DB):
    company = company_for(db, account)
    candidate = db.scalar(select(Candidate).where(Candidate.id == data.candidate_id).execution_options(populate_existing=True).with_for_update())
    if candidate:
        db.info.setdefault("processing_cache", {}).pop(candidate.id, None)
    require(candidate is not None and candidate.published and candidate.confirmed_grade is not None and processing_active(db, candidate),
            404, "CANDIDATE_UNAVAILABLE", "Карточка недоступна или снята с публикации.")
    require(company_processing_active(db, company, lock=True), 409, "COMPANY_UNAVAILABLE",
            "Компания временно недоступна: работодатель должен подтвердить email и согласие на обработку.")
    require(company.description.strip() and company.contact.strip(), 409, "COMPANY_PROFILE_REQUIRED", "Добавьте описание компании и контакт работодателя.")
    require(not db.scalar(select(CompanyBlock).where(CompanyBlock.candidate_id == candidate.id, CompanyBlock.company_id == company.id)),
            403, "COMPANY_BLOCKED", "Кандидат ограничил предложения от этой компании.")
    values = data.model_dump(mode="json")
    salary_valid(values)
    require(data.work_format in {"remote", "hybrid", "office", "any"}, detail="Неизвестный формат работы.")
    if data.need_id:
        need = db.get(Need, data.need_id)
        require(need is not None and need.company_id == company.id, 404, "NOT_FOUND", "Потребность не найдена.")
    if data.vacancy_id:
        vacancy = db.get(Vacancy, data.vacancy_id)
        require(vacancy is not None and vacancy.company_id == company.id, 404, "NOT_FOUND", "Вакансия не найдена.")
    if data.need_id:
        values["need_snapshot"] = need.data
    elif data.vacancy_id:
        values["need_snapshot"] = vacancy.data
    pending = db.scalar(select(Invitation).where(Invitation.company_id == company.id,
                        Invitation.candidate_id == candidate.id, Invitation.status == "pending"))
    require(pending is None or effective_status(pending) == "expired", 409, "INVITATION_DUPLICATE", "У кандидата уже есть активное приглашение от вашей компании.")
    count_today = len(db.scalars(select(Invitation).where(Invitation.company_id == company.id,
                                Invitation.created_at >= utcnow() - timedelta(days=1))).all())
    require(count_today < 100, 429, "INVITATION_LIMIT", "Дневной лимит приглашений исчерпан.")
    expiry = aware(data.expires_at) if data.expires_at else utcnow() + timedelta(days=7)
    require(utcnow() < expiry <= utcnow() + timedelta(days=30), detail="Срок предложения: от текущего момента до 30 дней.")
    values.pop("candidate_id", None)
    values.pop("need_id", None)
    values.pop("vacancy_id", None)
    values.pop("expires_at", None)
    row = Invitation(company_id=company.id, candidate_id=candidate.id, need_id=data.need_id,
        vacancy_id=data.vacancy_id, data=values, salary_from=data.salary_from, salary_to=data.salary_to,
        company_snapshot=company_dto(company), expires_at=expiry)
    db.add(row)
    db.flush()
    emit(db, candidate.account_id, "invitation.received", f"Предложение от {company.name}", {"invitation_id": row.id})
    audit(db, account, "invitation.created", row.id)
    return invitation_dto(db, row, account)


@router.get("/invitations/{invitation_id}")
def invitation(invitation_id: str, account: Verified, db: DB):
    row = owned_invitation(db, account, invitation_id, lock=account.role == "candidate")
    if account.role == "candidate" and not row.data.get("viewed_at"):
        row.data = {**row.data, "viewed_at": iso(utcnow())}
        emit(db, db.get(Company, row.company_id).account_id, "invitation.viewed",
             "Кандидат просмотрел приглашение", {"invitation_id": row.id})
        audit(db, account, "invitation.viewed", row.id)
    return invitation_dto(db, row, account)


def grant_contacts(db, candidate_id, company_id, source="invitation", invitation_id=None):
    grant = db.scalar(select(ContactGrant).where(ContactGrant.candidate_id == candidate_id,
                      ContactGrant.company_id == company_id).with_for_update())
    if grant:
        grant.revoked_at, grant.source, grant.invitation_id = None, source, invitation_id
    else:
        grant = ContactGrant(candidate_id=candidate_id, company_id=company_id, source=source, invitation_id=invitation_id)
        db.add(grant)
    db.flush()
    return grant


@router.post("/invitations/{invitation_id}/accept")
def accept(invitation_id: str, account: CandidateUser, db: DB):
    candidate = candidate_for(db, account)
    candidate = db.scalar(select(Candidate).where(Candidate.id == candidate.id).execution_options(populate_existing=True).with_for_update())
    require(processing_active(db,candidate),403,"PROCESSING_CONSENT_REQUIRED","Согласие на обработку было отозвано.")
    row = owned_invitation(db, account, invitation_id, lock=True)
    if row.status == "accepted":
        # Repeating an earlier acceptance never restores a revoked permission.
        return invitation_dto(db, row, account)
    require(effective_status(row) == "pending", 409, "INVITATION_CLOSED", "Предложение истекло, отозвано или уже обработано.")
    company = db.get(Company, row.company_id)
    require(company_processing_active(db, company, lock=True), 409, "COMPANY_UNAVAILABLE",
            "Компания временно недоступна: работодатель должен подтвердить email и согласие на обработку.")
    row.status, row.updated_at = "accepted", utcnow()
    grant = grant_contacts(db, row.candidate_id, row.company_id, invitation_id=row.id)
    emit(db, company.account_id, "invitation.accepted", "Кандидат принял приглашение", {"invitation_id": row.id})
    db.add(Outbox(kind="ats.invitation_accepted", payload={"invitation_id": row.id, "company_id": row.company_id,
                                                          "candidate_id": row.candidate_id, "grant_id": grant.id}))
    audit(db, account, "invitation.accepted", row.id, {"grant_id": grant.id})
    return invitation_dto(db, row, account)


@router.post("/invitations/{invitation_id}/decline")
def decline(invitation_id: str, account: CandidateUser, db: DB):
    row = owned_invitation(db, account, invitation_id, lock=True)
    if row.status == "declined":
        return invitation_dto(db, row, account)
    require(effective_status(row) == "pending", 409, "INVITATION_CLOSED", "Предложение уже обработано или истекло.")
    row.status, row.updated_at = "declined", utcnow()
    company = db.get(Company, row.company_id)
    emit(db, company.account_id, "invitation.declined", "Кандидат отклонил приглашение", {"invitation_id": row.id})
    audit(db, account, "invitation.declined", row.id)
    return invitation_dto(db, row, account)


@router.post("/invitations/{invitation_id}/withdraw")
def withdraw(invitation_id: str, account: EmployerUser, db: DB):
    row = owned_invitation(db, account, invitation_id, lock=True)
    if row.status == "withdrawn":
        return invitation_dto(db, row, account)
    require(effective_status(row) == "pending", 409, "INVITATION_CLOSED", "Предложение уже обработано или истекло.")
    row.status, row.updated_at = "withdrawn", utcnow()
    audit(db, account, "invitation.withdrawn", row.id)
    return invitation_dto(db, row, account)


class Message(BaseModel):
    text: str = Field(min_length=1, max_length=3000)


@router.post("/invitations/{invitation_id}/messages", status_code=201)
def message(invitation_id: str, data: Message, account: Verified, db: DB):
    row = owned_invitation(db, account, invitation_id)
    candidate = db.scalar(select(Candidate).where(Candidate.id == row.candidate_id)
                          .execution_options(populate_existing=True).with_for_update())
    db.info.setdefault("processing_cache", {}).pop(candidate.id, None)
    require(processing_active(db, candidate), 409, "CANDIDATE_UNAVAILABLE", "Переписка остановлена: кандидат отозвал обработку данных.")
    row = owned_invitation(db, account, invitation_id, lock=True)
    require(effective_status(row) in {"pending", "accepted"}, 409, "INVITATION_CLOSED", "Переписка закрыта для этого предложения.")
    require(company_processing_active(db, db.get(Company, row.company_id), lock=True), 409,
            "COMPANY_UNAVAILABLE", "Переписка остановлена: работодатель должен подтвердить email и согласие на обработку.")
    require(not db.scalar(select(CompanyBlock).where(CompanyBlock.candidate_id == row.candidate_id, CompanyBlock.company_id == row.company_id)),
            403, "COMPANY_BLOCKED", "Переписка с этой компанией ограничена.")
    db.add(InvitationMessage(invitation_id=row.id, account_id=account.id, text=data.text.strip()))
    recipient = db.get(Company, row.company_id).account_id if account.role == "candidate" else db.get(Candidate, row.candidate_id).account_id
    emit(db, recipient, "invitation.message", "Новое сообщение по предложению", {"invitation_id": row.id})
    audit(db, account, "invitation.message", row.id)
    db.flush()
    return invitation_dto(db, row, account)


@router.post("/invitations/{invitation_id}/report", status_code=201)
def report(invitation_id: str, data: Message, account: CandidateUser, db: DB):
    row = owned_invitation(db, account, invitation_id)
    issue = Report(account_id=account.id, invitation_id=row.id, reason=data.text)
    db.add(issue)
    db.flush()
    audit(db, account, "invitation.reported", row.id)
    return {"id": issue.id, "status": "received", "message": "Жалоба сохранена для проверки оператором."}


@router.post("/candidate/companies/{company_id}/block")
def block(company_id: str, account: CandidateUser, db: DB):
    candidate = candidate_for(db, account)
    db.scalar(select(Candidate).where(Candidate.id == candidate.id).with_for_update())
    require(db.get(Company, company_id), 404, "NOT_FOUND", "Компания не найдена.")
    if not db.scalar(select(CompanyBlock).where(CompanyBlock.candidate_id == candidate.id, CompanyBlock.company_id == company_id)):
        db.add(CompanyBlock(candidate_id=candidate.id, company_id=company_id))
    for row in db.scalars(select(Invitation).where(Invitation.candidate_id == candidate.id,
                         Invitation.company_id == company_id, Invitation.status == "pending")):
        row.status = "declined"
    grant = db.scalar(select(ContactGrant).where(ContactGrant.candidate_id == candidate.id, ContactGrant.company_id == company_id))
    if grant:
        grant.revoked_at = grant.revoked_at or utcnow()
    audit(db, account, "company.blocked", company_id)
    return {"company_id": company_id, "blocked": True}


@router.delete("/candidate/companies/{company_id}/block")
def unblock(company_id: str, account: CandidateUser, db: DB):
    candidate = candidate_for(db, account)
    row = db.scalar(select(CompanyBlock).where(CompanyBlock.candidate_id == candidate.id, CompanyBlock.company_id == company_id))
    if row:
        db.delete(row)
    audit(db, account, "company.unblocked", company_id)
    return {"company_id": company_id, "blocked": False}

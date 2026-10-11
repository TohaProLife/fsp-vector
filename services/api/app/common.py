from datetime import datetime, timezone
from typing import Annotated
from fastapi import Depends
from sqlalchemy import event, select
from sqlalchemy.orm import Session
from .db import get_db
from .models import Account, AuditEvent, Candidate, Company, CompanyBlock, Consent, ContactGrant, Notification, Outbox

DB = Annotated[Session, Depends(get_db, scope="function")]


class Problem(Exception):
    def __init__(self, status: int, code: str, detail: str):
        self.status, self.code, self.detail = status, code, detail


def require(condition, status=400, code="INVALID_INPUT", detail="Проверьте введённые данные."):
    if not condition:
        raise Problem(status, code, detail)


def aware(value: datetime | None):
    return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


def iso(value):
    return aware(value).isoformat() if value else None


def rows(items):
    return {"items": items, "total": len(items)}


def audit(db, account, action, entity=None, data=None):
    db.add(AuditEvent(account_id=account.id if account else None, action=action,
                      entity_id=entity, data=data or {}))


def emit(db, account_id, kind, title, data=None):
    notification = Notification(account_id=account_id, kind=kind, title=title, data=data or {})
    db.add(notification)
    db.flush()
    db.add(Outbox(kind="notification", payload={"notification_id": notification.id, "account_id": account_id}))
    return notification


def candidate_for(db, account):
    candidate = db.scalar(select(Candidate).where(Candidate.account_id == account.id))
    require(candidate is not None, 403, "ROLE_REQUIRED", "Этот раздел доступен кандидатам.")
    return candidate


def lock_candidate(db, account, require_processing=True):
    candidate = db.scalar(select(Candidate).where(Candidate.account_id == account.id)
                          .execution_options(populate_existing=True).with_for_update())
    require(candidate is not None,403,"ROLE_REQUIRED","Этот раздел доступен кандидатам.")
    db.info.setdefault("processing_cache",{}).pop(candidate.id,None)
    if require_processing:
        require(processing_active(db,candidate),403,"PROCESSING_CONSENT_REQUIRED","Согласие на обработку было отозвано.")
    return candidate


def company_for(db, account):
    company = db.scalar(select(Company).where(Company.account_id == account.id))
    require(company is not None, 403, "ROLE_REQUIRED", "Этот раздел доступен работодателям.")
    return company


def company_dto(company):
    return {"id": company.id, "name": company.name, "description": company.description,
            "industry": company.industry, "city": company.city, "website": company.website, "contact": company.contact,
            "team": company.team, "verification_status": "not_required_for_demo"}


def _clear_projection_access(db):
    for key in ("projection_access", "processing_cache", "account_cache"):
        db.info.pop(key, None)


def _permission_changes(db):
    return any(isinstance(row, (Account, Consent, ContactGrant, CompanyBlock))
               for collection in (db.new, db.dirty, db.deleted) for row in collection)


def _projection_permissions_flushed(db, _):
    if _permission_changes(db):
        _clear_projection_access(db)


def _projection_access(db):
    if not db.info.get("projection_access_flush_listener"):
        event.listen(db, "after_flush", _projection_permissions_flushed)
        db.info["projection_access_flush_listener"] = True
    cache = db.info.get("projection_access")
    if _permission_changes(db) or cache and cache["transaction"] is not db.get_transaction():
        _clear_projection_access(db)
        return None
    return cache


def prime_projection_access(db: Session, candidates, company=None) -> None:
    """Load projection permissions for one population in this request's session.

    With a company, this performs three SELECTs regardless of population size:
    accounts/latest processing consent, company blocks, and active contact grants.
    The snapshot is never shared across sessions or companies, and permission
    writes or a transaction boundary invalidate it. Unknown IDs in this scope
    fail closed; another company uses the ordinary single-candidate checks.
    """
    population = {row.id: row.account_id for row in candidates if row is not None}
    _clear_projection_access(db)
    _projection_access(db)
    accounts, processing, blocked, grants = {}, {}, set(), set()
    if population:
        latest = (select(Consent.granted).where(Consent.account_id == Account.id,
                  Consent.purpose == "processing").order_by(Consent.created_at.desc())
                  .limit(1).correlate(Account).scalar_subquery())
        loaded = db.execute(select(Account, latest.label("processing_granted"))
                            .where(Account.id.in_(set(population.values())))
                            .execution_options(populate_existing=True)).all()
        accounts = {account.id: account for account, _ in loaded}
        allowed = {account.id: bool(account.email_verified and granted)
                   for account, granted in loaded}
        processing = {candidate_id: allowed.get(account_id, False)
                      for candidate_id, account_id in population.items()}
        if company:
            blocked = set(db.scalars(select(CompanyBlock.candidate_id).where(
                CompanyBlock.company_id == company.id, CompanyBlock.candidate_id.in_(population))).all())
            grants = set(db.scalars(select(ContactGrant.candidate_id).where(
                ContactGrant.company_id == company.id, ContactGrant.candidate_id.in_(population),
                ContactGrant.revoked_at.is_(None))).all())
    db.info["processing_cache"] = processing
    db.info["account_cache"] = accounts
    db.info["projection_access"] = {"transaction": db.get_transaction(),
        "company_id": company.id if company else None, "population": population,
        "blocked": blocked, "grants": grants}


def _projection_scope(db, candidate, company):
    cache = _projection_access(db)
    return cache if cache and cache["company_id"] == (company.id if company else None) else None


def _known_projection_candidate(cache, candidate):
    return bool(candidate and candidate.id in cache["population"] and
                cache["population"][candidate.id] == candidate.account_id)


def company_blocked(db, candidate, company):
    if not candidate or not company:
        return False
    cache = _projection_scope(db, candidate, company)
    if cache is not None:
        return not _known_projection_candidate(cache, candidate) or candidate.id in cache["blocked"]
    return db.scalar(select(CompanyBlock.id).where(CompanyBlock.candidate_id == candidate.id,
                     CompanyBlock.company_id == company.id)) is not None


def has_grant(db, candidate, company):
    if not candidate or not company:
        return False
    cache = _projection_scope(db, candidate, company)
    if cache is not None:
        return _known_projection_candidate(cache, candidate) and candidate.id in cache["grants"]
    return db.scalar(select(ContactGrant).where(ContactGrant.candidate_id == candidate.id,
                  ContactGrant.company_id == company.id, ContactGrant.revoked_at.is_(None))) is not None


def processing_active(db, candidate):
    if not candidate:
        return False
    cache = _projection_access(db)
    if cache and candidate.id in cache["population"] and not _known_projection_candidate(cache, candidate):
        return False
    cached = db.info.get("processing_cache", {})
    if candidate.id in cached:
        return cached[candidate.id]
    account = db.info.get("account_cache", {}).get(candidate.account_id) or db.get(Account, candidate.account_id)
    consent = db.scalar(select(Consent).where(Consent.account_id == candidate.account_id,
                       Consent.purpose == "processing").order_by(Consent.created_at.desc()).limit(1))
    result = bool(account and account.email_verified and consent and consent.granted)
    db.info.setdefault("processing_cache", {})[candidate.id] = result
    return result


def company_processing_active(db, company, lock=False):
    """A company's new hiring actions require its verified, consenting owner.

    Mutations and transport hold the same owner row locked by consent changes.
    Do not cache this state across a rights check or an external dispatch.
    """
    if not company:
        return False
    query = select(Account).where(Account.id == company.account_id).execution_options(populate_existing=True)
    owner = db.scalar(query.with_for_update() if lock else query)
    consent = db.scalar(select(Consent).where(Consent.account_id == company.account_id,
        Consent.purpose == "processing").order_by(Consent.created_at.desc()).limit(1))
    return bool(owner and owner.role == "employer" and owner.email_verified and consent and consent.granted)


def private_content_reason(db, candidate, company):
    """Context text is private even when a historical record's state survives.

    Revoking a contact grant alone does not erase voluntarily supplied context.
    Processing withdrawal and company blocking stop its subsequent disclosure.
    """
    if not processing_active(db, candidate):
        return "processing_withdrawn"
    if company_blocked(db, candidate, company):
        return "company_blocked"
    return None


def candidate_accessible(db, candidate, company=None):
    cache = _projection_scope(db, candidate, company)
    if cache is not None and not _known_projection_candidate(cache, candidate):
        return False
    if company_blocked(db, candidate, company):
        return False
    return bool(candidate and processing_active(db, candidate) and
                ((candidate.published and candidate.confirmed_grade) or has_grant(db, candidate, company)))


def candidate_projection(db, candidate, company=None, own=False):
    _projection_access(db)
    if not own and not candidate_accessible(db, candidate, company):
        # Historical invitations, applications and company practice retain their
        # own state, but must not resurrect a withdrawn participant's profile.
        label = candidate.alias if processing_active(db, candidate) else "Карточка недоступна"
        return {"id": candidate.id, "alias": label, "name": label,
                "published": False, "contact_authorized": False, "profile_available": False}
    account = db.info.get("account_cache", {}).get(candidate.account_id) or db.get(Account, candidate.account_id)
    result = {"id": candidate.id, "alias": candidate.alias, "title": candidate.title,
              "city": candidate.city, "specialization": candidate.specialization,
              "declared_grade": candidate.declared_grade, "confirmed_grade": candidate.confirmed_grade,
              "category": f"{candidate.specialization}:{candidate.confirmed_grade}" if candidate.confirmed_grade else None,
              "score": candidate.score, "skills": candidate.skills, "preferences": candidate.preferences,
              "published": candidate.published, "evidence": [item for item in candidate.evidence if own or
                  item.get("source") != "NEED_PRACTICE_OBSERVED" or
                  company and item.get("scope", {}).get("company_id") == company.id], "fsp": candidate.fsp,
              "achievements": candidate.fsp.get("achievements", []), "assessment_at": iso(candidate.assessment_at),
              "source": "synthetic_fixture" if candidate.fixture else "participant",
              "updated_at": iso(candidate.updated_at)}
    if own or (processing_active(db, candidate) and has_grant(db, candidate, company)):
        result.update({"name": account.name, "bio": candidate.bio,
                       "contacts": {"email": account.email, **candidate.contacts}, "contact_authorized": True})
    else:
        result.update({"name": candidate.alias, "bio": "", "contact_authorized": False})
    if own:
        result.update({"survey": candidate.survey})
    return result


def salary_valid(data):
    low, high = data.get("salary_from"), data.get("salary_to")
    require(isinstance(low, (int, float)) and not isinstance(low, bool) and
            isinstance(high, (int, float)) and not isinstance(high, bool),
            detail="Укажите зарплатный диапазон от и до в рублях.")
    require(0 < low <= high <= 10_000_000, detail="Зарплата: 0 < от ≤ до ≤ 10 000 000 ₽.")


def notification_dto(row):
    return {"id": row.id, "kind": row.kind, "title": row.title, "data": row.data,
            "read": row.read, "created_at": iso(row.created_at)}

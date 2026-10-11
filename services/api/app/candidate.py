import io
import asyncio
import re
from pathlib import Path
from fastapi import APIRouter, Body, File, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, update
from .auth import CandidateUser, User, digest
from .common import DB, audit, candidate_for, candidate_projection, company_dto, emit, iso, lock_candidate, notification_dto, processing_active, require, salary_valid
from .config import settings
from .models import Account, AssessmentAttempt, AuditEvent, Candidate, Company, CompanyBlock, Consent, ContactGrant, FspRecord, Invitation, MatchRun, Notification, utcnow
from .pdf_import import PdfImportFailure, parse_pdf_isolated

router = APIRouter(prefix="/candidate", tags=["Candidate & passport"])


def history_dto(row):
    return {"id": row.id, "specialization": row.specialization, "grade": row.grade, "status": row.status,
            "demo": row.demo, "started_at": iso(row.started_at), "finished_at": iso(row.finished_at),
            "result": row.result, "score": row.result.get("score") if row.result else None,
            "passed": row.result.get("passed") if row.result else False,
            "scope": row.private_form.get("scope", "global_category"),
            "context": row.private_form.get("context")}


def survey_history_dto(db, account, limit=100, offset=0):
    entries = db.scalars(select(AuditEvent).where(AuditEvent.account_id == account.id,
        AuditEvent.action == "survey.completed").order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(limit).offset(offset)).all()
    return [{"id": row.id, "created_at": iso(row.created_at),
             "taxonomy_version": row.data.get("taxonomy_version"),
             "answers": row.data.get("answers"),
             "snapshot_available": bool(row.data.get("answers"))} for row in entries]


def expire_owned_attempts(db, candidate):
    # The history view is also a lifecycle read. Expiration is anchored to the
    # issued deadline, never to the date a participant next opens the profile.
    # The conditional update cannot overwrite a concurrently completed attempt.
    db.execute(update(AssessmentAttempt).where(
        AssessmentAttempt.candidate_id == candidate.id,
        AssessmentAttempt.status == "in_progress",
        AssessmentAttempt.expires_at <= utcnow(),
    ).values(status="expired", finished_at=AssessmentAttempt.expires_at))


def own_profile(db, account):
    candidate = candidate_for(db, account)
    expire_owned_attempts(db, candidate)
    result = candidate_projection(db, candidate, own=True)
    result["history"] = [history_dto(row) for row in db.scalars(select(AssessmentAttempt).where(
        AssessmentAttempt.candidate_id == candidate.id).order_by(AssessmentAttempt.started_at.desc(), AssessmentAttempt.id.desc()).limit(30))]
    result["confirmed_categories"] = candidate.confirmed_categories
    result["survey_history"] = survey_history_dto(db, account)
    if settings.local_demo and account.email == "candidate@vector.local":
        result["fsp"] = {**result["fsp"], "demo_identity": {"fsp_id": "FSP-DEMO-001", "proof_code": "VECTOR-2026"}}
    result["contact_grants"] = [{"id": row.id, "company_id": row.company_id,
        "company_name": db.get(Company, row.company_id).name, "source": row.source,
        "active": row.revoked_at is None, "created_at": iso(row.created_at), "revoked_at": iso(row.revoked_at)}
        for row in db.scalars(select(ContactGrant).where(ContactGrant.candidate_id == candidate.id))]
    result["blocked_companies"] = [{"id": row.company_id, "company_id": row.company_id,
        "name": db.get(Company, row.company_id).name, "created_at": iso(row.created_at)}
        for row in db.scalars(select(CompanyBlock).where(CompanyBlock.candidate_id == candidate.id))]
    return result


@router.get("/profile")
def profile(account: CandidateUser, db: DB):
    return own_profile(db, account)


class ProfilePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=2, max_length=120)
    alias: str | None = Field(default=None, min_length=2, max_length=80)
    title: str | None = Field(default=None, max_length=200)
    bio: str | None = Field(default=None, max_length=5000)
    city: str | None = Field(default=None, max_length=120)
    skills: list[str] | None = Field(default=None, max_length=40)
    preferences: dict | None = None
    contacts: dict | None = None


@router.patch("/profile")
def update_profile(data: ProfilePatch, account: CandidateUser, db: DB):
    candidate = lock_candidate(db,account)
    values = data.model_dump(exclude_unset=True)
    for key, value in values.items():
        require(value is not None, detail="Поля профиля не могут быть null.")
        if key == "name":
            account.name = value.strip()
        elif key == "preferences":
            allowed = {"salary_from", "salary_to", "work_format", "employment"}
            require(set(value) <= allowed, detail="Неизвестное поле предпочтений.")
            merged = {**candidate.preferences, **value}
            if merged.get("salary_from") is not None or merged.get("salary_to") is not None:
                salary_valid(merged)
            require(merged.get("work_format", "any") in {"remote", "hybrid", "office", "any"}, detail="Неизвестный формат работы.")
            candidate.preferences = merged
        elif key == "contacts":
            require(set(value) <= {"phone", "telegram", "website", "github"}, detail="Email меняется только через проверку адреса.")
            require(all(isinstance(item, str) and len(item) <= 300 for item in value.values()), detail="Проверьте контакты.")
            candidate.contacts = {**candidate.contacts, **value}
        elif key == "skills":
            require(all(1 <= len(item) <= 80 for item in value), detail="Название навыка: от 1 до 80 символов.")
            candidate.skills = list(dict.fromkeys(value))
        else:
            setattr(candidate, key, value)
    candidate.updated_at = utcnow()
    audit(db, account, "profile.updated", candidate.id, {"fields": list(values)})
    return own_profile(db, account)


class Survey(BaseModel):
    industry: str = Field(min_length=1, max_length=120)
    specialization: str = Field(min_length=1, max_length=40)
    grade: str = Field(min_length=1, max_length=20)
    stack: list[str] = Field(min_length=1, max_length=20)
    work_format: str = "remote"


@router.post("/survey")
def survey(data: Survey, account: CandidateUser, db: DB):
    from .engines.assessment import catalog
    taxonomy = catalog()
    require(data.specialization in {item["id"] for item in taxonomy["specializations"]}, detail="Выберите доступную специализацию.")
    grades = {item["id"] if isinstance(item, dict) else item for item in taxonomy["grades"]}
    require(data.grade in grades, detail="Выберите доступный грейд.")
    require(data.work_format in {"remote", "hybrid", "office", "any"}, detail="Неизвестный формат работы.")
    candidate = lock_candidate(db,account)
    candidate.survey = data.model_dump()
    candidate.specialization, candidate.declared_grade = data.specialization, data.grade
    previous = candidate.confirmed_categories.get(data.specialization)
    candidate.confirmed_grade = previous.get("grade") if previous else None
    candidate.score = previous.get("score") if previous else None
    candidate.assessment_at = None
    if previous and previous.get("confirmed_at"):
        from datetime import datetime
        candidate.assessment_at = datetime.fromisoformat(previous["confirmed_at"])
    candidate.preferences = {**candidate.preferences, "work_format": data.work_format}
    if candidate.confirmed_grade is None:
        candidate.published = False
    audit(db, account, "survey.completed", candidate.id,
          {"taxonomy_version": taxonomy["blueprint_version"], "answers": candidate.survey})
    return own_profile(db, account)


class Publication(BaseModel):
    published: bool
    consent_publication: bool = False


@router.post("/publication")
def publication(data: Publication, account: CandidateUser, db: DB):
    candidate = lock_candidate(db,account)
    if data.published:
        require(candidate.confirmed_grade is not None, 409, "CATEGORY_REQUIRED", "Сначала подтвердите выбранный грейд экзаменом.")
        require(data.consent_publication, 400, "PUBLICATION_CONSENT_REQUIRED", "Для публикации карточки нужно отдельное согласие.")
    candidate.published = data.published
    db.add(Consent(account_id=account.id, purpose="publication", granted=data.published))
    audit(db, account, "publication.changed", candidate.id, {"published": data.published})
    return own_profile(db, account)


@router.get("/consents")
def consents(account: User, db: DB):
    from .practice import practice_notifications_allowed
    candidate_for(db, account)
    records = db.scalars(select(Consent).where(Consent.account_id == account.id).order_by(Consent.created_at.desc())).all()
    latest = {}
    for row in records:
        latest.setdefault(row.purpose, row.granted)
    return {"current": latest, "effective_practice_notifications": practice_notifications_allowed(db, account),
        "items": [{"id": row.id, "purpose": row.purpose, "granted": row.granted,
        "version": row.version, "created_at": iso(row.created_at)} for row in records], "version": "2026-10-07"}


class ConsentChange(BaseModel):
    purpose: str
    granted: bool


@router.post("/consents")
def consent_change(data: ConsentChange, account: User, db: DB):
    candidate = lock_candidate(db,account,require_processing=False)
    require(data.purpose in {"processing", "publication", "fsp", "practice"}, detail="Неизвестная цель согласия.")
    if data.granted and data.purpose in {"publication", "fsp", "practice"}:
        require(processing_active(db, candidate), 409, "PROCESSING_CONSENT_REQUIRED", "Сначала подтвердите email и согласие на обработку.")
    if data.granted and data.purpose == "publication":
        require(candidate.confirmed_grade is not None, 409, "CATEGORY_REQUIRED", "Сначала подтвердите грейд.")
    db.add(Consent(account_id=account.id, purpose=data.purpose, granted=data.granted))
    if data.purpose == "publication":
        candidate.published = data.granted
    if not data.granted and data.purpose == "processing":
        candidate.published = False
        for grant in db.scalars(select(ContactGrant).where(ContactGrant.candidate_id == candidate.id, ContactGrant.revoked_at.is_(None))):
            grant.revoked_at = utcnow()
        for invite in db.scalars(select(Invitation).where(Invitation.candidate_id == candidate.id, Invitation.status == "pending")):
            invite.status = "withdrawn_by_candidate"
    if not data.granted and data.purpose in {"processing", "fsp"}:
        candidate.fsp = {"status": "revoked", "source": "FSP_DEMO_CONFIRMED", "achievements": []}
        candidate.evidence = [e for e in candidate.evidence if e.get("source") not in {"FSP_DEMO_CONFIRMED", "FSP_REGISTRY_VERIFIED"}]
    audit(db, account, "consent.changed", candidate.id, {"purpose": data.purpose, "granted": data.granted})
    db.flush()
    return consents(account, db)


@router.post("/contact-grants/{grant_id}/revoke")
def revoke(grant_id: str, account: CandidateUser, db: DB):
    candidate = lock_candidate(db,account)
    grant = db.scalar(select(ContactGrant).where(ContactGrant.id == grant_id).with_for_update())
    require(grant is not None and grant.candidate_id == candidate.id, 404, "NOT_FOUND", "Разрешение не найдено.")
    grant.revoked_at = grant.revoked_at or utcnow()
    emit(db, db.get(Company, grant.company_id).account_id, "contact_grant.revoked", "Кандидат отозвал доступ к контактам", {"candidate_id": candidate.id})
    audit(db, account, "contact_grant.revoked", grant.id)
    return {"id": grant.id, "active": False, "revoked_at": iso(grant.revoked_at),
            "message": "Дальнейшая выдача контактов прекращена. Ранее просмотренные данные удалить у получателя невозможно."}


class FspLink(BaseModel):
    fsp_id: str = Field(max_length=100)
    proof_code: str = Field(max_length=100)


@router.post("/fsp/link")
def fsp_link(data: FspLink, account: CandidateUser, db: DB):
    candidate = lock_candidate(db,account)
    require(settings.local_demo, 503, "FSP_UNAVAILABLE", "Официальный API реестра пока не предоставлен.")
    record = db.get(FspRecord, data.fsp_id)
    require(record is not None and record.email == account.email and record.proof_hash == digest(data.proof_code),
            403, "FSP_OWNERSHIP_FAILED", "ID или код подтверждения не соответствует вашему аккаунту в демонстрационном реестре.")
    candidate.fsp = {"status": "verified_demo", "source": "FSP_DEMO_CONFIRMED", "fsp_id": record.fsp_id,
                     "achievements": record.achievements, "synced_at": iso(utcnow()), "demo": True}
    db.add(Consent(account_id=account.id, purpose="fsp", granted=True))
    audit(db, account, "fsp.linked_demo", candidate.id)
    return {"fsp": candidate.fsp, "message": "Привязан демонстрационный реестр. Это синтетические достижения."}


@router.delete("/fsp/link")
def fsp_unlink(account: CandidateUser, db: DB):
    candidate = lock_candidate(db,account)
    candidate.fsp = {"status": "not_linked", "achievements": []}
    candidate.evidence = [e for e in candidate.evidence if e.get("source") not in {"FSP_DEMO_CONFIRMED", "FSP_REGISTRY_VERIFIED"}]
    db.add(Consent(account_id=account.id, purpose="fsp", granted=False))
    audit(db, account, "fsp.unlinked", candidate.id)
    return {"fsp": candidate.fsp}


@router.get("/history")
def history(account: CandidateUser, db: DB, page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100)):
    candidate = candidate_for(db, account)
    expire_owned_attempts(db, candidate)
    query = select(AssessmentAttempt).where(AssessmentAttempt.candidate_id == candidate.id)
    total = db.scalar(select(func.count()).select_from(AssessmentAttempt).where(AssessmentAttempt.candidate_id == candidate.id))
    attempts = db.scalars(query.order_by(AssessmentAttempt.started_at.desc(), AssessmentAttempt.id.desc())
        .limit(page_size).offset((page - 1) * page_size)).all()
    return {"items": [history_dto(row) for row in attempts], "total": total, "page": page, "page_size": page_size}


@router.get("/survey-history")
def survey_history(account: CandidateUser, db: DB, page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100)):
    total = db.scalar(select(func.count()).select_from(AuditEvent).where(
        AuditEvent.account_id == account.id, AuditEvent.action == "survey.completed"))
    return {"items": survey_history_dto(db, account, page_size, (page - 1) * page_size),
            "total": total, "page": page, "page_size": page_size}


@router.get("/passport")
def passport(account: CandidateUser, db: DB):
    return {**own_profile(db, account), "passport_version": "vector-passport-v1", "calibration_status": "expert_initial",
            "limitations": "Подтверждение относится к проверенному стеку. Демо-достижения не являются данными реального реестра ФСП."}


@router.get("/dashboard")
def dashboard(account: CandidateUser, db: DB):
    from .hiring import invitation_dto
    candidate = candidate_for(db, account)
    invites = db.scalars(select(Invitation).where(Invitation.candidate_id == candidate.id).order_by(Invitation.created_at.desc())).all()
    actions = []
    if not candidate.survey:
        actions.append({"id": "survey", "title": "Выберите специализацию и предполагаемый грейд", "href": "/workspace/assessment"})
    if not candidate.confirmed_grade:
        actions.append({"id": "assessment", "title": "Подтвердите компетенции экзаменом", "href": "/workspace/assessment"})
    elif not candidate.published:
        actions.append({"id": "publication", "title": "Откройте карточку работодателям", "href": "/workspace/privacy"})
    notes = db.scalars(select(Notification).where(Notification.account_id == account.id).order_by(Notification.created_at.desc()).limit(5)).all()
    return {"profile": own_profile(db, account), "stats": {"invitations": len(invites),
        "active_invitations": sum(row.status == "pending" for row in invites),
        "assessments": len(own_profile(db, account)["history"]), "confirmed_competencies": len(candidate.evidence)},
        "invitations": [invitation_dto(db, row, account) for row in invites[:5]],
        "recommended_actions": actions, "notifications": [notification_dto(row) for row in notes]}


@router.post("/resume-import")
async def resume_import(account: CandidateUser, db: DB, file: UploadFile = File(...)):
    content = await file.read(settings.upload_limit + 1)
    require(len(content) <= settings.upload_limit, 413, "UPLOAD_TOO_LARGE", "PDF не должен превышать 3 МБ.")
    require(content.startswith(b"%PDF-"), 415, "PDF_REQUIRED", "Выберите PDF-файл.")
    try:
        # No ORM/session enters this thread. It only supervises a trusted bounded
        # parser child, keeping decompression away from the API event loop.
        parsed = await asyncio.to_thread(parse_pdf_isolated,content)
    except PdfImportFailure as exc:
        details = {"PDF_ENCRYPTED":"Выберите PDF без шифрования.",
            "PDF_PAGE_LIMIT":"PDF должен содержать от 1 до 15 страниц.",
            "PDF_PARSE_TIMEOUT":"Безопасный лимит чтения PDF истёк. Заполните профиль вручную.",
            "PDF_PARSER_BUSY":"Все обработчики PDF заняты. Повторите через несколько секунд.",
            "PDF_PARSER_ISOLATION_UNAVAILABLE":"Не удалось ограничить ресурсы обработчика PDF. Заполните профиль вручную.",
            "PDF_PARSER_UNAVAILABLE":"Обработчик PDF временно недоступен. Заполните профиль вручную."}
        require(False,503 if exc.code in {"PDF_PARSER_BUSY","PDF_PARSER_UNAVAILABLE","PDF_PARSER_ISOLATION_UNAVAILABLE"} else 422 if exc.code == "PDF_PARSE_TIMEOUT" else 400,
                exc.code,details.get(exc.code,"Не удалось безопасно прочитать PDF. Заполните профиль вручную."))
    text = parsed["text"]
    require(len(text.strip()) >= 20, 422, "PDF_NO_TEXT", "В PDF нет читаемого текста. Для скана заполните профиль вручную.")
    vocabulary = ["Python", "TypeScript", "JavaScript", "React", "SQL", "PostgreSQL", "Docker", "Linux", "Kubernetes", "FastAPI", "Git", "Redis", "CI/CD", "pytest", "Terraform"]
    skills,spans = [],[]
    for skill in vocabulary:
        match = re.search(r"(?<!\w)" + re.escape(skill) + r"(?!\w)",text,re.I)
        if match:
            skills.append(skill)
            spans.append({"field":"skills","value":skill,"quote":match.group(0),
                          "start":match.start(),"end":match.end(),"offset_unit":"unicode_codepoint","source":"pdf_text"})
    candidate = candidate_for(db, account)
    draft = {"title": next((line.strip() for line in text.splitlines() if len(line.strip()) > 5), "")[:200],
             "bio": text[:3000], "skills": skills}
    audit(db, account, "resume.imported_draft", candidate.id, {"bytes": len(content), "pages": parsed["pages"]})
    return {"draft": draft, "profile": draft, "source": "SELF_DECLARED", "persisted": False,
            "source_spans": spans,"source_text":text,
            "message": "Проверьте извлечённые значения и сохраните профиль. Импорт не подтверждает навыки."}


@router.get("/profile.pdf")
def profile_pdf(account: CandidateUser, db: DB):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas
    candidate = candidate_for(db, account)
    font = "Helvetica"
    for path in (Path(__file__).resolve().parents[3] / "assets/fonts/GolosText-Regular.ttf",
                 Path("C:/Windows/Fonts/arial.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")):
        if path.exists():
            font = "VectorUnicode"
            if font not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(font, str(path)))
            break
    require(font != "Helvetica", 503, "PDF_FONT_UNAVAILABLE", "Для PDF требуется Unicode-шрифт. Установите DejaVu Sans.")
    stream = io.BytesIO()
    pdf = canvas.Canvas(stream, pagesize=A4)
    pdf.setTitle("ФСП Вектор — паспорт компетенций")
    category = candidate.confirmed_categories.get(candidate.specialization, {})
    category_origin = " · синтетический пример" if category.get("source") == "SYNTHETIC_SEED" or category.get("calibration_status") == "synthetic_fixture" else ""
    fsp_status = candidate.fsp.get("status", "not_linked")
    fsp_origin = " · демонстрационный реестр" if candidate.fsp.get("demo") or candidate.fsp.get("source") == "FSP_DEMO_CONFIRMED" else ""
    lines = ["ФСП ВЕКТОР · ПАСПОРТ КОМПЕТЕНЦИЙ", account.name, candidate.title,
             f"Специализация: {candidate.specialization or 'не выбрана'}",
             f"Заявленный грейд: {candidate.declared_grade or '—'}",
             f"Категория в паспорте: {candidate.confirmed_grade or 'не подтверждена'}{category_origin}",
             f"Навыки (заявлены): {', '.join(candidate.skills)}", f"Email: {account.email}",
             f"ФСП: {fsp_status}{fsp_origin}"]
    lines += [f"Свидетельство: {e.get('skill', e.get('competency',''))} · {pdf_evidence_label(e)}" for e in candidate.evidence]
    lines += ["", "Демо-источники синтетические. Паспорт не является гарантией найма."]
    import textwrap
    y = 795
    for line in lines:
        for part in textwrap.wrap(line, width=84) or [""]:
            if y < 50:
                pdf.showPage()
                y = 795
            pdf.setFont(font, 10)
            pdf.drawString(42, y, part)
            y -= 19
    pdf.save()
    audit(db, account, "profile.pdf_exported", candidate.id)
    return Response(stream.getvalue(), media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=vector-passport.pdf"})


def pdf_evidence_label(evidence):
    """PDF exports retain the same provenance distinctions as the passport UI."""
    source = evidence.get("source", "")
    scope = evidence.get("scope") or {}
    synthetic = (evidence.get("origin") == "SYNTHETIC_SEED" or source == "SYNTHETIC_SEED" or
                 scope.get("mode") == "synthetic_fixture" or evidence.get("calibration_status") == "synthetic_fixture")
    status = str(evidence.get("status", "active")).strip().lower()
    if synthetic:
        label = "Синтетический пример"
    elif evidence.get("is_demo"):
        label = "Демонстрационная проверка"
    elif source == "ASSESSMENT_VERIFIED":
        label = "Экзамен · подтверждено" if status in {"verified", "active"} else "Экзамен · статус не подтверждён"
    else:
        label = {"SELF_DECLARED": "Заявлено участником", "PRACTICE_OBSERVED": "Практика · наблюдение",
                 "NEED_PRACTICE_OBSERVED": "Практика компании · наблюдение",
                 "COMPANY_REVIEWED": "Субъективная оценка компании",
                 "FSP_DEMO_CONFIRMED": "Демонстрационный реестр ФСП",
                 "FSP_REGISTRY_VERIFIED": "Реестр ФСП"}.get(source, "Источник не подтверждён")
    if evidence.get("revoked") or status in {"revoked", "record_revoked"}:
        label += " · свидетельство отозвано"
    elif status in {"stale", "sync_stale"}:
        label += " · свидетельство устарело"
    if scope.get("global_grade") is False or source in {"PRACTICE_OBSERVED", "NEED_PRACTICE_OBSERVED", "COMPANY_REVIEWED"}:
        label += " · не присваивает глобальный грейд"
    return label

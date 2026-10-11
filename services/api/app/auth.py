import hashlib
import hmac
import secrets
from datetime import timedelta
from typing import Annotated, Literal
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select
from .common import DB, audit, aware, candidate_for, company_for, iso, require, rows
from .config import settings
from .models import Account, BrowserSession, Candidate, Company, Consent, EmailVerification, LoginFailure, MailMessage, Outbox, utcnow

router = APIRouter(prefix="/auth", tags=["Identity & access"])

PUBLISHED_DEMO_PASSWORD = "VectorDemo2026!"


def synthetic_identity(account, db):
    if account.email.endswith("@vector.local"):
        return True
    candidate = db.scalar(select(Candidate).where(Candidate.account_id == account.id))
    return bool(candidate and candidate.fixture)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def hash_password(password):
    salt = secrets.token_hex(16)
    value = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 450_000).hex()
    return f"pbkdf2_sha256$450000${salt}${value}"


def check_password(password, stored):
    try:
        _, rounds, salt, value = stored.split("$")
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(rounds)).hex()
        return hmac.compare_digest(actual, value)
    except (ValueError, TypeError):
        return False


def check_origin(request):
    origin = request.headers.get("origin")
    if origin:
        parsed = urlparse(origin)
        allowed = {settings.frontend_url}
        if settings.local_demo:
            allowed.update({"http://localhost:3000", "http://127.0.0.1:3000", str(request.base_url).rstrip("/")})
        require(origin.rstrip("/") in allowed and parsed.scheme in {"http", "https"},
                403, "ORIGIN_REJECTED", "Запрос получен с недоверенного адреса.")


def current_user(request: Request, db: DB):
    token = request.cookies.get("vector_session")
    require(bool(token), 401, "AUTH_REQUIRED", "Войдите в аккаунт.")
    session = db.scalar(select(BrowserSession).where(BrowserSession.token_hash == digest(token)))
    require(session is not None and aware(session.expires_at) > utcnow(), 401, "SESSION_EXPIRED", "Сессия завершена. Войдите снова.")
    account = db.get(Account, session.account_id)
    require(account is not None, 401, "AUTH_REQUIRED", "Войдите в аккаунт.")
    require(settings.local_demo or not synthetic_identity(account, db),
            401, "AUTH_REQUIRED", "Демонстрационные аккаунты доступны только на локальном стенде.")
    request.state.browser_session = session
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        check_origin(request)
        csrf = request.headers.get("x-csrf-token", "")
        require(csrf.isascii() and hmac.compare_digest(csrf, session.csrf_token), 403, "CSRF_REJECTED", "Обновите страницу и повторите действие.")
    return account


User = Annotated[Account, Depends(current_user)]


def verified_user(account: User, db: DB):
    require(account.email_verified, 403, "EMAIL_NOT_VERIFIED", "Подтвердите email в письме, прежде чем продолжить.")
    consent = db.scalar(select(Consent).where(Consent.account_id == account.id,
                       Consent.purpose == "processing").order_by(Consent.created_at.desc()).limit(1))
    require(consent is not None and consent.granted, 403, "PROCESSING_CONSENT_REQUIRED",
            "Для работы с профилем нужно согласие на обработку данных.")
    return account


Verified = Annotated[Account, Depends(verified_user)]


def candidate_user(account: Verified, db: DB):
    candidate_for(db, account)
    return account


def employer_user(account: Verified, db: DB):
    company_for(db, account)
    return account


CandidateUser = Annotated[Account, Depends(candidate_user)]
EmployerUser = Annotated[Account, Depends(employer_user)]


def me_dto(db, account, session):
    candidate = db.scalar(select(Candidate).where(Candidate.account_id == account.id))
    company = db.scalar(select(Company).where(Company.account_id == account.id))
    processing = db.scalar(select(Consent).where(Consent.account_id == account.id, Consent.purpose == "processing").order_by(Consent.created_at.desc()).limit(1))
    return {"id": account.id, "name": account.name, "email": account.email, "role": account.role,
            "consent_processing": bool(processing and processing.granted),
            "email_verified": account.email_verified, "csrf_token": session.csrf_token,
            "candidate_id": candidate.id if candidate else None, "company_id": company.id if company else None}


class Register(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=12, max_length=128)
    role: Literal["candidate", "employer"]
    consent_processing: bool


class Login(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)


def send_verification(db, account):
    token = secrets.token_urlsafe(40)
    db.add(EmailVerification(account_id=account.id, token_hash=digest(token), expires_at=utcnow() + timedelta(hours=24)))
    url = f"{settings.frontend_url}/verify?token={token}"
    mail = MailMessage(to=account.email, subject="Подтвердите email — ФСП Вектор",
        body=f"Здравствуйте, {account.name}. Подтвердите адрес: {url}\nСсылка действительна 24 часа.", verification_url=url,
        delivery_status="queued" if settings.smtp_host else "local_inbox_available" if settings.local_demo else "transport_not_configured")
    db.add(mail)
    db.flush()
    if settings.smtp_host or not settings.local_demo:
        db.add(Outbox(kind="email.verification", payload={"mail_id": mail.id}))


@router.post("/register", status_code=201)
def register(data: Register, request: Request, db: DB):
    check_origin(request)
    email = data.email.strip().lower()
    require("@" in email and "." in email.split("@")[-1], detail="Введите корректный email.")
    require(settings.local_demo or not email.endswith("@vector.local"),
            detail="Демонстрационный домен зарезервирован для локального стенда.")
    require(settings.local_demo or data.password != PUBLISHED_DEMO_PASSWORD,
            detail="Выберите пароль, отличный от опубликованного демонстрационного.")
    require(data.consent_processing, detail="Подтвердите отдельное согласие на обработку данных.")
    require(db.scalar(select(Account).where(Account.email == email)) is None, 409, "EMAIL_EXISTS", "Этот email уже зарегистрирован.")
    account = Account(name=data.name.strip(), email=email, password_hash=hash_password(data.password), role=data.role)
    db.add(account)
    db.flush()
    if data.role == "candidate":
        db.add(Candidate(account_id=account.id, alias=f"Участник {secrets.token_hex(3).upper()}", contacts={"email": email}))
    else:
        db.add(Company(account_id=account.id, contact=email))
    db.add(Consent(account_id=account.id, purpose="processing", granted=True))
    send_verification(db, account)
    audit(db, account, "account.register")
    return {"id": account.id, "email": email, "email_verified": False,
            "message": "Письмо подготовлено. Подтвердите email, затем войдите.", "delivery": "queued_smtp" if settings.smtp_host else "local_mailbox" if settings.local_demo else "pending_transport"}


@router.post("/login")
def login(data: Login, request: Request, response: Response, db: DB):
    check_origin(request)
    bucket, network = digest(data.email.strip().lower()), digest(request.client.host if request.client else "unknown")
    recent = utcnow() - timedelta(minutes=15)
    failures = db.scalar(select(func.count()).select_from(LoginFailure).where(LoginFailure.identity_bucket == bucket, LoginFailure.created_at >= recent))
    network_failures = db.scalar(select(func.count()).select_from(LoginFailure).where(LoginFailure.network_bucket == network, LoginFailure.created_at >= recent))
    require(failures < 10 and network_failures < 50, 429, "LOGIN_THROTTLED", "Слишком много попыток входа. Повторите через 15 минут.")
    account = db.scalar(select(Account).where(Account.email == data.email.strip().lower()))
    stored = account.password_hash if account else "pbkdf2_sha256$450000$00000000000000000000000000000000$" + "0" * 64
    password_valid = check_password(data.password, stored)
    production_allowed = settings.local_demo or bool(account and not synthetic_identity(account, db) and data.password != PUBLISHED_DEMO_PASSWORD)
    if not (password_valid and account is not None and production_allowed):
        db.add(LoginFailure(identity_bucket=bucket, network_bucket=network))
        db.execute(delete(LoginFailure).where(LoginFailure.created_at < utcnow() - timedelta(days=1)))
        # The failed security event must survive the subsequent error rollback.
        db.commit()
        require(False, 401, "INVALID_CREDENTIALS", "Неверный email или пароль.")
    db.execute(delete(LoginFailure).where(LoginFailure.identity_bucket == bucket))
    token = secrets.token_urlsafe(48)
    session = BrowserSession(account_id=account.id, token_hash=digest(token), csrf_token=secrets.token_urlsafe(32),
                             expires_at=utcnow() + timedelta(days=settings.session_days))
    db.add(session)
    db.flush()
    response.set_cookie("vector_session", token, httponly=True, secure=settings.cookie_secure,
                        samesite="lax", max_age=settings.session_days * 86400, path="/")
    audit(db, account, "session.login")
    return me_dto(db, account, session)


@router.get("/me")
def me(request: Request, account: User, db: DB):
    return me_dto(db, account, request.state.browser_session)


@router.post("/logout")
def logout(request: Request, response: Response, account: User, db: DB):
    db.delete(request.state.browser_session)
    response.delete_cookie("vector_session", path="/")
    audit(db, account, "session.logout")
    return {"ok": True}


@router.get("/verify")
def verify(token: str, db: DB):
    row = db.scalar(select(EmailVerification).where(EmailVerification.token_hash == digest(token)).with_for_update())
    require(row is not None and not row.used and aware(row.expires_at) > utcnow(), 400, "VERIFICATION_EXPIRED", "Ссылка использована или истекла. Запросите новое письмо.")
    account = db.get(Account, row.account_id)
    account.email_verified, row.used = True, True
    audit(db, account, "email.verified")
    return {"email_verified": True, "email": account.email}


@router.post("/resend-verification")
def resend(account: User, db: DB):
    require(not account.email_verified, 409, "ALREADY_VERIFIED", "Email уже подтверждён.")
    send_verification(db, account)
    return {"ok": True, "delivery": "local_mailbox" if settings.local_demo else "pending_smtp"}


@router.get("/demo-mailbox")
def mailbox(email: str, db: DB):
    require(settings.local_demo, 404, "NOT_FOUND", "Демо-почта отключена.")
    emails = db.scalars(select(MailMessage).where(MailMessage.to == email.strip().lower()).order_by(MailMessage.created_at.desc()).limit(20)).all()
    return rows([{"id": row.id, "to": row.to, "subject": row.subject, "body": row.body,
                  "verification_url": row.verification_url, "created_at": iso(row.created_at), "source": "local_demo_mailbox",
                  "delivery_status": row.delivery_status, "delivered_at": iso(row.delivered_at)} for row in emails])


class ProcessingConsent(BaseModel):
    consent_processing: bool


@router.get("/consents")
def identity_consents(account: User, db: DB):
    processing = db.scalar(select(Consent).where(Consent.account_id == account.id,
        Consent.purpose == "processing").order_by(Consent.created_at.desc()).limit(1))
    return {"consent_processing": bool(processing and processing.granted), "version": "2026-10-07"}


@router.post("/consents")
def identity_consent(data: ProcessingConsent, account: User, db: DB):
    require(account.email_verified or not data.consent_processing, 409, "EMAIL_NOT_VERIFIED", "Сначала подтвердите email.")
    if account.role == "candidate":
        from .candidate import ConsentChange, consent_change
        consent_change(ConsentChange(purpose="processing",granted=data.consent_processing), account, db)
    else:
        # New hiring actions/ATS dispatch lock this same owner before checking
        # the latest consent, so withdrawal cannot race an unchecked action.
        db.scalar(select(Account).where(Account.id == account.id).execution_options(populate_existing=True).with_for_update())
        db.add(Consent(account_id=account.id, purpose="processing", granted=data.consent_processing))
        audit(db, account, "consent.changed", data={"purpose":"processing","granted":data.consent_processing})
    return {"consent_processing": data.consent_processing, "version": "2026-10-07"}

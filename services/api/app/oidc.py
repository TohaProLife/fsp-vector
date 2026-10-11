"""Authorization Code + PKCE BFF adapter; browser never receives provider tokens."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import base64
import hashlib
import hmac
import os
import secrets
from typing import Literal
from urllib.parse import urlencode, urlparse

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
import httpx
import jwt
from sqlalchemy import DateTime, ForeignKey, JSON, String, UniqueConstraint, delete, select
from sqlalchemy.orm import Mapped, mapped_column

from .auth import digest, hash_password
from .common import DB, audit, aware, require
from .config import settings
from .db import Base
from .models import Account, BrowserSession, Candidate, Company, Consent, utcnow, new_id

router = APIRouter(prefix="/auth/oidc", tags=["OpenID Connect"])


@dataclass(frozen=True)
class OidcConfig:
    issuer: str = os.getenv("OIDC_ISSUER", "").rstrip("/")
    client_id: str = os.getenv("OIDC_CLIENT_ID", "vector-web")
    client_secret: str = os.getenv("OIDC_CLIENT_SECRET", "")
    redirect_uri: str = os.getenv("OIDC_REDIRECT_URI", "http://localhost:3000/api/v1/auth/oidc/callback")
    internal_issuer: str = os.getenv("OIDC_INTERNAL_ISSUER", "").rstrip("/")


config = OidcConfig()


def production_config_errors() -> list[str]:
    if settings.local_demo or not (config.issuer or config.client_secret):
        return []
    errors = []
    issuer = urlparse(config.issuer)
    redirect = urlparse(config.redirect_uri)
    if issuer.scheme != "https" or not issuer.hostname or issuer.username or issuer.query or issuer.fragment:
        errors.append("OIDC_ISSUER must be a trusted HTTPS issuer")
    if not config.client_secret:
        errors.append("OIDC_CLIENT_SECRET is required for the confidential BFF client")
    if redirect.scheme != "https" or config.redirect_uri != settings.frontend_url + "/api/v1/auth/oidc/callback":
        errors.append("OIDC_REDIRECT_URI must match the HTTPS frontend callback")
    if config.internal_issuer:
        internal = urlparse(config.internal_issuer)
        if internal.scheme != "https" or not internal.hostname or internal.username or internal.password or internal.query or internal.fragment:
            errors.append("OIDC_INTERNAL_ISSUER must use trusted HTTPS transport in production")
    return errors


def transport_url(url: str) -> str:
    """Container-only transport override; public issuer validation remains exact."""
    if config.internal_issuer and (url == config.issuer or url.startswith(config.issuer + "/")):
        return config.internal_issuer + url[len(config.issuer):]
    return url


class OIDCState(Base):
    __tablename__ = "oidc_states"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    binding_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)
    expires_at: Mapped[object] = mapped_column(DateTime(timezone=True))


class ExternalIdentity(Base):
    __tablename__ = "external_identities"
    __table_args__ = (UniqueConstraint("issuer", "subject"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    issuer: Mapped[str] = mapped_column(String(500))
    subject: Mapped[str] = mapped_column(String(200))
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))


class OIDCSession(Base):
    __tablename__ = "oidc_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    browser_session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), unique=True)
    issuer: Mapped[str] = mapped_column(String(500))
    subject: Mapped[str] = mapped_column(String(200))
    provider_sid: Mapped[str | None] = mapped_column(String(200), nullable=True)


class OIDCLogoutEvent(Base):
    __tablename__ = "oidc_logout_events"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    expires_at: Mapped[object] = mapped_column(DateTime(timezone=True))


def discovery() -> dict:
    require(bool(config.issuer and config.client_secret), 503, "OIDC_DISABLED", "Единый вход ещё не настроен. Используйте email и пароль.")
    require(not production_config_errors(), 503, "OIDC_UNSAFE_CONFIG", "Конфигурация единого входа требует проверки администратором.")
    try:
        with httpx.Client(timeout=8, follow_redirects=False) as client:
            response = client.get(transport_url(config.issuer + "/.well-known/openid-configuration"))
            response.raise_for_status()
            data = response.json()
        require(data.get("issuer") == config.issuer, 503, "OIDC_ISSUER_MISMATCH", "Источник входа не прошёл проверку.")
        if not settings.local_demo:
            for field in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
                endpoint = urlparse(str(data.get(field, "")))
                require(endpoint.scheme == "https" and bool(endpoint.hostname) and not endpoint.username,
                        503, "OIDC_UNSAFE_CONFIG", "Конфигурация единого входа требует проверки администратором.")
        return data
    except httpx.HTTPError:
        require(False, 503, "OIDC_UNAVAILABLE", "Сервис единого входа недоступен. Используйте email и пароль.")


def validated_claims(token: str, metadata: dict, *, nonce: str | None = None) -> dict:
    try:
        header = jwt.get_unverified_header(token)
        require(header.get("alg") == "RS256", 400, "OIDC_INVALID_TOKEN", "Источник входа не прошёл проверку.")
        with httpx.Client(timeout=8) as client:
            response = client.get(transport_url(metadata["jwks_uri"]))
            response.raise_for_status()
            jwks = jwt.PyJWKSet.from_dict(response.json())
        key = next(key for key in jwks.keys if key.key_id == header.get("kid"))
        claims = jwt.decode(token, key.key, algorithms=["RS256"], audience=config.client_id,
                            issuer=config.issuer, leeway=10,
                            options={"require": ["exp", "iat", "iss", "aud", "sub"]})
        audience = claims.get("aud")
        if isinstance(audience, list) and len(audience) > 1:
            require(claims.get("azp") == config.client_id, 400, "OIDC_INVALID_TOKEN", "Источник входа не прошёл проверку.")
        if nonce is not None:
            require(hmac.compare_digest(str(claims.get("nonce", "")), nonce), 400, "OIDC_NONCE_MISMATCH", "Повторите вход из этого браузера.")
        return claims
    except (jwt.PyJWTError, StopIteration, KeyError, ValueError, httpx.HTTPError):
        require(False, 400, "OIDC_INVALID_TOKEN", "Не удалось проверить источник входа. Начните вход заново.")


@router.get("/status")
def status():
    return {"enabled": bool(config.issuer and config.client_secret), "issuer": config.issuer or None,
            "identity_source": "local_keycloak_demo" if settings.local_demo else "configured_oidc",
            "fsp_registry_connected": False}


@router.get("/login")
def login(db: DB, role: Literal["candidate", "employer"] = "candidate"):
    metadata = discovery()
    state, binding = secrets.token_urlsafe(40), secrets.token_urlsafe(40)
    verifier, nonce = secrets.token_urlsafe(64), secrets.token_urlsafe(32)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    db.add(OIDCState(id=digest(state), binding_hash=digest(binding), payload={"verifier": verifier, "nonce": nonce, "role": role},
                     expires_at=utcnow() + timedelta(minutes=10)))
    db.execute(delete(OIDCState).where(OIDCState.expires_at < utcnow()))
    query = urlencode({"client_id": config.client_id, "redirect_uri": config.redirect_uri, "response_type": "code",
                       "scope": "openid profile email", "state": state, "nonce": nonce,
                       "code_challenge": challenge, "code_challenge_method": "S256"})
    response = RedirectResponse(metadata["authorization_endpoint"] + "?" + query, status_code=302)
    response.set_cookie("vector_oidc_binding", binding, httponly=True, secure=settings.cookie_secure, samesite="lax", max_age=600, path="/api/v1/auth/oidc")
    return response


@router.get("/callback")
def callback(request: Request, db: DB, state: str = "", code: str = "", error: str | None = None):
    require(not error, 400, "OIDC_CANCELLED", "Вход отменён. Можно войти с email и паролем.")
    row = db.scalar(select(OIDCState).where(OIDCState.id == digest(state)).with_for_update())
    binding = request.cookies.get("vector_oidc_binding", "")
    require(row is not None and aware(row.expires_at) > utcnow() and
            hmac.compare_digest(row.binding_hash, digest(binding)), 400, "OIDC_STATE_MISMATCH", "Вход истёк или открыт в другом браузере. Начните заново.")
    require(bool(code) and len(code) < 4000, 400, "OIDC_INVALID_CODE", "Не получено подтверждение входа.")
    metadata = discovery()
    try:
        with httpx.Client(timeout=10) as client:
            response = client.post(transport_url(metadata["token_endpoint"]), data={"grant_type": "authorization_code", "code": code,
                "redirect_uri": config.redirect_uri, "client_id": config.client_id, "client_secret": config.client_secret,
                "code_verifier": row.payload["verifier"]})
            response.raise_for_status()
            tokens = response.json()
        claims = validated_claims(tokens["id_token"], metadata, nonce=row.payload["nonce"])
    except (httpx.HTTPError, KeyError, ValueError):
        require(False, 400, "OIDC_CODE_REJECTED", "Подтверждение входа истекло. Начните заново.")
    require(claims.get("email_verified") is True, 403, "EMAIL_NOT_VERIFIED", "Сначала подтвердите email в сервисе единого входа.")
    identity = db.scalar(select(ExternalIdentity).where(ExternalIdentity.issuer == config.issuer, ExternalIdentity.subject == claims["sub"]))
    email = str(claims.get("email", "")).strip().lower()
    require("@" in email and len(email) <= 254, 400, "OIDC_EMAIL_REQUIRED", "Сервис входа не предоставил подтверждённый email.")
    require(settings.local_demo or not email.endswith("@vector.local"),
            403, "DEMO_IDENTITY_DISABLED", "Демонстрационные аккаунты доступны только в локальном стенде.")
    if identity:
        account = db.get(Account, identity.account_id)
    else:
        account = db.scalar(select(Account).where(Account.email == email))
        # Linking requires both identities to have independently verified this email.
        require(account is None or account.email_verified, 409, "OIDC_LINK_REQUIRES_VERIFIED_ACCOUNT", "Подтвердите email существующего аккаунта, затем повторите единый вход.")
        if account is None:
            account = Account(name=str(claims.get("name") or email.split("@")[0])[:120], email=email,
                              role=row.payload["role"], email_verified=True, password_hash=hash_password(secrets.token_urlsafe(48)))
            db.add(account)
            db.flush()
            if account.role == "candidate":
                db.add(Candidate(account_id=account.id, alias=f"Участник {secrets.token_hex(3).upper()}", contacts={"email": email}))
            else:
                db.add(Company(account_id=account.id, contact=email))
        db.add(ExternalIdentity(issuer=config.issuer, subject=claims["sub"], account_id=account.id))
    require(settings.local_demo or not account.email.lower().endswith("@vector.local"),
            403, "DEMO_IDENTITY_DISABLED", "Демонстрационные аккаунты доступны только в локальном стенде.")
    db.delete(row)
    token = secrets.token_urlsafe(48)
    session = BrowserSession(account_id=account.id, token_hash=digest(token), csrf_token=secrets.token_urlsafe(32),
                             expires_at=utcnow() + timedelta(days=settings.session_days))
    db.add(session)
    db.flush()
    db.add(OIDCSession(browser_session_id=session.id, issuer=config.issuer, subject=claims["sub"], provider_sid=claims.get("sid")))
    consent = db.scalar(select(Consent).where(Consent.account_id == account.id, Consent.purpose == "processing").order_by(Consent.created_at.desc()).limit(1))
    target = "/workspace/overview" if consent and consent.granted else "/workspace/privacy"
    audit(db, account, "session.oidc_login", data={"issuer": config.issuer})
    redirect = RedirectResponse(settings.frontend_url + target, status_code=302)
    redirect.set_cookie("vector_session", token, httponly=True, secure=settings.cookie_secure, samesite="lax", max_age=settings.session_days * 86400, path="/")
    redirect.delete_cookie("vector_oidc_binding", path="/api/v1/auth/oidc")
    return redirect


@router.post("/backchannel-logout")
def backchannel_logout(db: DB, logout_token: str = Form(max_length=24000)):
    metadata = discovery()
    claims = validated_claims(logout_token, metadata)
    require("nonce" not in claims and bool(claims.get("jti")) and "http://schemas.openid.net/event/backchannel-logout" in claims.get("events", {}),
            400, "OIDC_INVALID_LOGOUT", "Некорректное завершение сессии.")
    event_id = digest(config.issuer + "|" + claims["jti"])
    if db.get(OIDCLogoutEvent, event_id):
        return {"ok": True}
    from datetime import datetime, timezone
    db.add(OIDCLogoutEvent(id=event_id, expires_at=datetime.fromtimestamp(claims["exp"], tz=timezone.utc)))
    db.execute(delete(OIDCLogoutEvent).where(OIDCLogoutEvent.expires_at < utcnow()))
    query = select(OIDCSession).where(OIDCSession.issuer == config.issuer, OIDCSession.subject == claims["sub"])
    if claims.get("sid"):
        query = query.where(OIDCSession.provider_sid == claims["sid"])
    for row in db.scalars(query).all():
        session = db.get(BrowserSession, row.browser_session_id)
        db.delete(row)
        if session:
            db.delete(session)
    return {"ok": True}

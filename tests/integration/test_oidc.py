"""Security properties of the real OIDC adapter using signed test-provider tokens."""
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import time
from dataclasses import replace
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
import jwt
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import oidc
from app.auth import hash_password
from app.db import Base, get_db
from app.main import app
from app.models import Account, BrowserSession, Consent

ISSUER = "https://identity.example.test/realms/vector"


@pytest.fixture
def protocol(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)

    def db_override():
        with sessions() as db:
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise

    app.dependency_overrides[get_db] = db_override
    client = TestClient(app)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = key.public_key().public_numbers()

    def b64(number):
        return base64.urlsafe_b64encode(number.to_bytes((number.bit_length() + 7) // 8, "big")).rstrip(b"=").decode()

    metadata = {"issuer": ISSUER, "authorization_endpoint": ISSUER + "/auth", "token_endpoint": ISSUER + "/token", "jwks_uri": ISSUER + "/certs"}
    provider = {"nonce": None, "overrides": {}, "code_verifier": None}

    def signed(claims=None):
        payload = {"iss": ISSUER, "aud": "vector-web", "sub": "test-subject", "iat": int(time.time()),
                   "exp": int(time.time()) + 300, "nonce": provider["nonce"], "sid": "test-sid",
                   "email": "oidc@example.test", "email_verified": True, "name": "Тестовый участник"}
        payload.update(provider["overrides"])
        payload.update(claims or {})
        if payload.get("nonce") is None:
            payload.pop("nonce", None)
        return jwt.encode(payload, key, algorithm="RS256", headers={"kid": "test-key"})

    class Result:
        def __init__(self, payload):
            self.payload = payload
        def json(self):
            return self.payload
        def raise_for_status(self):
            pass

    class ProviderClient:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def get(self, url):
            if url.endswith("openid-configuration"):
                return Result(metadata)
            assert url == metadata["jwks_uri"]
            return Result({"keys": [{"kty": "RSA", "use": "sig", "alg": "RS256", "kid": "test-key", "n": b64(public.n), "e": b64(public.e)}]})
        def post(self, url, data):
            assert url == metadata["token_endpoint"]
            assert data["client_secret"] == "test-client-secret"
            provider["code_verifier"] = data["code_verifier"]
            return Result({"id_token": signed(), "access_token": "never-exposed-token"})

    monkeypatch.setattr(oidc, "config", oidc.OidcConfig(issuer=ISSUER, client_id="vector-web", client_secret="test-client-secret"))
    monkeypatch.setattr(oidc.httpx, "Client", ProviderClient)
    with sessions() as db:
        account = Account(name="Тест", email="oidc@example.test", role="candidate", email_verified=True,
                          password_hash=hash_password("test-password-123!"))
        db.add(account)
        db.flush()
        db.add(Consent(account_id=account.id, purpose="processing", granted=True))
        db.commit()

    def begin():
        response = client.get("/api/v1/auth/oidc/login", follow_redirects=False)
        assert response.status_code == 302
        query = parse_qs(urlparse(response.headers["location"]).query)
        provider["nonce"] = query["nonce"][0]
        return query

    yield client, sessions, provider, begin, signed
    app.dependency_overrides.clear()
    engine.dispose()


def test_signed_code_flow_pkce_cookie_and_no_provider_token(protocol):
    client, sessions, provider, begin, _ = protocol
    query = begin()
    response = client.get("/api/v1/auth/oidc/callback", params={"state": query["state"][0], "code": "provider-code"}, follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"].endswith("/workspace/overview")
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "never-exposed-token" not in response.text + str(response.headers)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(provider["code_verifier"].encode()).digest()).rstrip(b"=").decode()
    assert challenge == query["code_challenge"][0]
    assert client.get("/api/v1/auth/me").status_code == 200
    replay = client.get("/api/v1/auth/oidc/callback", params={"state": query["state"][0], "code": "provider-code"}, follow_redirects=False)
    assert replay.status_code == 400


def test_state_browser_binding_is_required(protocol):
    client, sessions, provider, begin, _ = protocol
    query = begin()
    client.cookies.delete("vector_oidc_binding")
    response = client.get("/api/v1/auth/oidc/callback", params={"state": query["state"][0], "code": "provider-code"})
    assert response.status_code == 400
    assert response.json()["code"] == "OIDC_STATE_MISMATCH"


@pytest.mark.parametrize("overrides", [{"nonce": "wrong"}, {"iss": "https://evil.example.test"}, {"aud": "other-client"},
                                        {"exp": 1}, {"email_verified": False}])
def test_bad_identity_claims_never_create_session(protocol, overrides):
    client, sessions, provider, begin, _ = protocol
    query = begin()
    provider["overrides"] = overrides
    response = client.get("/api/v1/auth/oidc/callback", params={"state": query["state"][0], "code": "provider-code"}, follow_redirects=False)
    assert response.status_code in (400, 403)
    with sessions() as db:
        assert db.scalar(select(BrowserSession)) is None


def test_backchannel_logout_invalidates_session_and_rejects_id_token(protocol):
    client, sessions, provider, begin, signed = protocol
    query = begin()
    assert client.get("/api/v1/auth/oidc/callback", params={"state": query["state"][0], "code": "provider-code"}, follow_redirects=False).status_code == 302
    assert client.post("/api/v1/auth/oidc/backchannel-logout", data={"logout_token": signed()}).status_code == 400
    token = signed({"nonce": None, "jti": "logout-1", "events": {"http://schemas.openid.net/event/backchannel-logout": {}}})
    assert client.post("/api/v1/auth/oidc/backchannel-logout", data={"logout_token": token}).status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.post("/api/v1/auth/oidc/backchannel-logout", data={"logout_token": token}).status_code == 200


def test_production_rejects_verified_demo_identity(protocol, monkeypatch):
    client, sessions, provider, begin, _ = protocol
    query = begin()
    monkeypatch.setattr(oidc, "settings", SimpleNamespace(local_demo=False, frontend_url="https://app.example.test"))
    monkeypatch.setattr(oidc, "config", replace(oidc.config, redirect_uri="https://app.example.test/api/v1/auth/oidc/callback"))
    provider["overrides"] = {"email": "candidate@vector.local"}
    response = client.get("/api/v1/auth/oidc/callback", params={"state":query["state"][0],"code":"provider-code"}, follow_redirects=False)
    assert response.status_code == 403
    assert response.json()["code"] == "DEMO_IDENTITY_DISABLED"
    with sessions() as db:
        assert db.scalar(select(BrowserSession)) is None
        assert db.scalar(select(Account).where(Account.email=="candidate@vector.local")) is None


@pytest.mark.parametrize("issuer,redirect", [
    ("http://identity.example.test/realms/vector", "https://app.example.test/api/v1/auth/oidc/callback"),
    (ISSUER, "http://app.example.test/api/v1/auth/oidc/callback"),
    (ISSUER, "https://other.example.test/api/v1/auth/oidc/callback"),
])
def test_production_unsafe_oidc_config_fails_before_provider_request(protocol, monkeypatch, issuer, redirect):
    client, _, _, _, _ = protocol
    monkeypatch.setattr(oidc, "settings", SimpleNamespace(local_demo=False, frontend_url="https://app.example.test"))
    monkeypatch.setattr(oidc, "config", replace(oidc.config, issuer=issuer, redirect_uri=redirect))
    response = client.get("/api/v1/auth/oidc/login", follow_redirects=False)
    assert response.status_code == 503
    assert response.json()["code"] == "OIDC_UNSAFE_CONFIG"

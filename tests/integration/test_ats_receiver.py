import hashlib
import hmac
import json
import sys
import time
from pathlib import Path
from fastapi.testclient import TestClient
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from services.integrations.receiver import app


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("ATS_WEBHOOK_SECRET", "v" * 64)
    monkeypatch.setenv("ATS_RECEIVER_DB", str(tmp_path / "receipts.db"))
    return TestClient(app)


def signed(payload, event_id="event-1", when=None):
    raw = json.dumps(payload, separators=(",", ":")).encode()
    timestamp = str(int(time.time()) if when is None else when)
    signature = hmac.new(("v" * 64).encode(), timestamp.encode() + b"." + raw, hashlib.sha256).hexdigest()
    return raw, {"X-Vector-Timestamp": timestamp, "X-Vector-Signature": signature,
                 "X-Vector-Event-Id": event_id, "Content-Type": "application/json"}


def test_delivery_is_signed_and_idempotent(client):
    raw, headers = signed({"company_id": "c1", "candidate_id": "p1", "kind": "invitation.accepted"})
    first = client.post("/events", content=raw, headers=headers)
    second = client.post("/events", content=raw, headers=headers)
    assert first.status_code == second.status_code == 200
    assert first.json()["duplicate"] is False
    assert second.json()["duplicate"] is True
    changed, headers = signed({"company_id": "another"})
    assert client.post("/events", content=changed, headers=headers).status_code == 409


def test_forgery_and_old_signature_are_rejected(client):
    raw, headers = signed({"company_id": "c1"})
    headers["X-Vector-Signature"] = "0" * 64
    assert client.post("/events", content=raw, headers=headers).status_code == 401
    raw, headers = signed({"company_id": "c1"}, when=int(time.time()) - 301)
    assert client.post("/events", content=raw, headers=headers).status_code == 401


def test_unscoped_payload_rejected(client):
    raw, headers = signed({"email": "must-not-pass@example.test"})
    assert client.post("/events", content=raw, headers=headers).status_code == 422

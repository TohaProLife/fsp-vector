"""Signed, bounded, idempotent demo ATS inbox; no external employer contacted."""
from __future__ import annotations
import hashlib
import hmac
import json
import os
from pathlib import Path
import sqlite3
import time
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from services.common.http import bounded_body

app = FastAPI(title="Vector local ATS receiver", docs_url=None, redoc_url=None)
ROOT = Path(__file__).resolve().parents[2]


def connect():
    path = Path(os.getenv("ATS_RECEIVER_DB", str(ROOT / ".local" / "ats-inbox.sqlite3")))
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.execute("CREATE TABLE IF NOT EXISTS receipts (id TEXT PRIMARY KEY, body_hash TEXT NOT NULL, payload TEXT NOT NULL, received_at INTEGER NOT NULL)")
    return db


def verify(raw, timestamp, signature, secret):
    try:
        fresh = abs(time.time() - int(timestamp)) <= 300
    except ValueError:
        fresh = False
    calculated = hmac.new(secret.encode(), timestamp.encode() + b"." + raw, hashlib.sha256).hexdigest()
    return len(secret) >= 32 and fresh and hmac.compare_digest(calculated, signature.removeprefix("sha256="))


@app.get("/health")
def health():
    return {"status": "ok", "kind": "local_demo_ats", "signature": "hmac_sha256_timestamp_body", "idempotent": True}


@app.post("/events")
async def event(request: Request):
    raw = await bounded_body(request, 64 * 1024)
    secret = os.getenv("ATS_WEBHOOK_SECRET", "")
    if not verify(raw, request.headers.get("x-vector-timestamp", ""), request.headers.get("x-vector-signature", ""), secret):
        raise HTTPException(401, "Signature invalid or expired")
    event_id = request.headers.get("x-vector-event-id", "")
    if not event_id or len(event_id) > 100:
        raise HTTPException(422, "Event ID required")
    try:
        payload = json.loads(raw)
    except ValueError:
        raise HTTPException(422, "Invalid JSON")
    if not isinstance(payload, dict) or not payload.get("company_id"):
        raise HTTPException(422, "Company-scoped payload required")
    fingerprint = hashlib.sha256(raw).hexdigest()
    with connect() as db:
        existing = db.execute("SELECT body_hash FROM receipts WHERE id=?", (event_id,)).fetchone()
        if existing:
            if existing[0] != fingerprint:
                raise HTTPException(409, "Event ID reused with different payload")
            return {"accepted": True, "duplicate": True, "event_id": event_id}
        db.execute("INSERT INTO receipts VALUES (?,?,?,?)", (event_id, fingerprint, json.dumps(payload, ensure_ascii=False), int(time.time())))
    return {"accepted": True, "duplicate": False, "event_id": event_id}

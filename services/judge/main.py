"""Authenticated gateway to a separately provisioned Linux execution VM."""
from __future__ import annotations
import hashlib
import hmac
import json
import os
import threading
import time
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from services.common.http import bounded_body
from .runner import readiness, run_submission

app = FastAPI(title="Vector isolated judge", docs_url=None, redoc_url=None, openapi_url=None)
cache: dict[str, tuple[float, dict]] = {}
cache_lock = threading.Lock()


class Submission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-f0-9-]{36}$")
    task_id: str = Field(max_length=80)
    language: str = Field(max_length=20)
    source: str = Field(max_length=32_000)


def authenticate(raw: bytes, timestamp: str, signature: str):
    secret = os.getenv("JUDGE_SHARED_SECRET", "")
    try:
        valid_time = abs(time.time() - int(timestamp)) <= 30
    except ValueError:
        valid_time = False
    calculated = hmac.new(secret.encode(), timestamp.encode() + b"." + raw, hashlib.sha256).hexdigest()
    if len(secret) < 32 or not valid_time or not hmac.compare_digest(calculated, signature):
        raise HTTPException(401, "Invalid gateway signature")


@app.get("/ready")
def ready():
    # Non-sensitive deployment readiness; network access restricted to the API host.
    return readiness()


@app.post("/submissions")
async def submit(request: Request):
    raw = await bounded_body(request, 80_000)
    authenticate(raw, request.headers.get("x-vector-timestamp", ""), request.headers.get("x-vector-signature", ""))
    try:
        data = Submission.model_validate_json(raw)
    except ValidationError:
        raise HTTPException(422, "Invalid submission fields")
    fingerprint = hashlib.sha256(raw).hexdigest()
    with cache_lock:
        for key, (when, _) in list(cache.items()):
            if when < time.time() - 300:
                del cache[key]
        if data.id in cache:
            record = cache[data.id][1]
            if record["fingerprint"] != fingerprint:
                raise HTTPException(409, "Submission ID conflict")
            if record["result"] is None:
                raise HTTPException(409, "Submission already in progress")
            return record["result"]
        if len(cache) >= 1000:
            raise HTTPException(503, "Replay cache full")
        cache[data.id] = (time.time(), {"fingerprint": fingerprint, "result": None})
    # Source is passed only to the isolated adapter, never exec/eval/imported by this process.
    import asyncio
    try:
        result = await asyncio.to_thread(run_submission, data.task_id, data.language, data.source)
    except ValueError:
        result = {"status": "invalid_submission", "passed": False, "changes_category": False}
    except Exception:
        result = {"status": "infrastructure_error", "passed": False, "changes_category": False}
    with cache_lock:
        cache[data.id] = (time.time(), {"fingerprint": fingerprint, "result": result})
    return result

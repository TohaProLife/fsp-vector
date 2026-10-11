"""BFF adapter for programming practice; availability fails closed on Windows."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import time
from uuid import uuid4
import httpx
from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import DateTime, ForeignKey, JSON, String, select
from sqlalchemy.orm import Mapped, mapped_column
from .auth import CandidateUser
from .common import DB, audit, candidate_for, iso, require, rows
from .db import Base
from .models import utcnow

# Shared trusted task definitions are data only; no runner imported in the API.
import importlib.util
_spec = importlib.util.spec_from_file_location("vector_trusted_programming_tasks", Path(__file__).resolve().parents[2] / "judge" / "tasks.py")
_tasks = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_tasks)
router = APIRouter(prefix="/judge", tags=["Isolated programming practice"])


class JudgeSubmission(Base):
    __tablename__ = "judge_submissions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id"), index=True)
    task_id: Mapped[str] = mapped_column(String(80))
    language: Mapped[str] = mapped_column(String(20))
    source_hash: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)


def gateway():
    endpoint, secret = os.getenv("JUDGE_URL", "").rstrip("/"), os.getenv("JUDGE_SHARED_SECRET", "")
    return (endpoint, secret) if endpoint.startswith(("http://", "https://")) and len(secret) >= 32 else (None, None)


def gateway_status():
    endpoint, _ = gateway()
    if not endpoint:
        return {"available": False, "reason": "isolated_linux_judge_not_configured", "languages": [], "native_fallback": False}
    try:
        response = httpx.get(f"{endpoint}/ready", timeout=3, follow_redirects=False)
        response.raise_for_status()
        state = response.json()
        return {**state, "native_fallback": False}
    except (httpx.HTTPError, ValueError):
        return {"available": False, "reason": "isolated_judge_unreachable", "languages": [], "native_fallback": False}


@router.get("/status")
def status():
    return gateway_status()


@router.get("/tasks")
def tasks(account: CandidateUser):
    return {**rows(_tasks.public_catalog()), "runtime": gateway_status()}


class Submit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: str = Field(max_length=80)
    language: str = Field(max_length=20)
    source: str = Field(min_length=1, max_length=32_000)


@router.post("/submissions", status_code=201)
def submit(data: Submit, account: CandidateUser, db: DB):
    require(data.task_id in _tasks.TASKS and data.language in {"python", "javascript"}, 422, "UNSUPPORTED_PROGRAMMING_TASK", "Выберите поддерживаемую задачу и язык.")
    require(len(data.source.encode()) <= 32_000, 413, "SOURCE_TOO_LARGE", "Исходный код превышает лимит 32 КБ.")
    state = gateway_status()
    require(state.get("available") and state.get("isolation") == "gvisor_runsc", 503, "ISOLATED_JUDGE_UNAVAILABLE", "Изолированный Linux judge недоступен. Локальные задачи на SQL и данные доступны в Практике.")
    candidate = candidate_for(db, account)
    row = JudgeSubmission(candidate_id=candidate.id, task_id=data.task_id, language=data.language,
                          source_hash=hashlib.sha256(data.source.encode()).hexdigest())
    db.add(row)
    db.flush()
    endpoint, secret = gateway()
    raw = json.dumps({"id": row.id, **data.model_dump()}, ensure_ascii=False, separators=(",", ":")).encode()
    timestamp = str(int(time.time()))
    signature = hmac.new(secret.encode(), timestamp.encode() + b"." + raw, hashlib.sha256).hexdigest()
    try:
        response = httpx.post(f"{endpoint}/submissions", content=raw,
            headers={"Content-Type": "application/json", "X-Vector-Timestamp": timestamp, "X-Vector-Signature": signature},
            timeout=35, follow_redirects=False)
        response.raise_for_status()
        result = response.json()
        # Allowlist avoids proxying hidden cases or arbitrary service output.
        row.result = {key: result.get(key) for key in ("status", "passed", "passed_cases", "total_cases", "elapsed_ms", "isolation", "checker_version")}
        row.result["changes_category"] = False
    except (httpx.HTTPError, ValueError):
        row.result = {"status": "infrastructure_error", "passed": False, "changes_category": False}
    audit(db, account, "programming.practice", row.id, {"task_id": row.task_id, "status": row.result.get("status")})
    return {"id": row.id, "task_id": row.task_id, "language": row.language, "result": row.result, "created_at": iso(row.created_at)}


@router.get("/submissions")
def submissions(account: CandidateUser, db: DB):
    candidate = candidate_for(db, account)
    return rows([{"id": row.id, "task_id": row.task_id, "language": row.language, "result": row.result, "created_at": iso(row.created_at)}
                 for row in db.scalars(select(JudgeSubmission).where(JudgeSubmission.candidate_id == candidate.id).order_by(JudgeSubmission.created_at.desc()).limit(100))])

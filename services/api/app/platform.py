import asyncio
import json
from datetime import timedelta
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select
from .auth import EmployerUser, Verified
from .common import DB, aware, company_for, iso, notification_dto, require, rows
from .config import settings
from .db import SessionLocal
from .models import Account, AssessmentAttempt, BrowserSession, Candidate, Consent, ContactGrant, Delivery, Invitation, MatchRun, Notification, Outbox, utcnow

router = APIRouter(tags=["Notifications & operations"])


@router.get("/notifications")
def notifications(account: Verified, db: DB):
    items = db.scalars(select(Notification).where(Notification.account_id == account.id).order_by(Notification.created_at.desc()).limit(100)).all()
    return {**rows([notification_dto(row) for row in items]), "unread": sum(not row.read for row in items)}


class ReadNotifications(BaseModel):
    ids: list[str] = Field(default_factory=list, max_length=100)
    all: bool = False


@router.post("/notifications/read")
def read_notifications(data: ReadNotifications, account: Verified, db: DB):
    query = select(Notification).where(Notification.account_id == account.id)
    if not data.all:
        query = query.where(Notification.id.in_(data.ids))
    items = db.scalars(query).all()
    for row in items:
        row.read = True
    return {"read": len(items)}


def event_updates(account_id, session_id, cursor, cursor_id=""):
    """Own short-lived DB session; safe to call in a thread without ORM leakage."""
    with SessionLocal() as db:
        account = db.get(Account, account_id)
        browser = db.get(BrowserSession, session_id)
        consent = db.scalar(select(Consent).where(Consent.account_id == account_id,
            Consent.purpose == "processing").order_by(Consent.created_at.desc()).limit(1))
        if not (account and account.email_verified and browser and browser.account_id == account_id and
                aware(browser.expires_at) > utcnow() and consent and consent.granted):
            return None
        query = select(Notification).where(Notification.account_id == account_id,
            or_(Notification.created_at > cursor,
                and_(Notification.created_at == cursor, Notification.id > cursor_id)))
        return [{"timestamp": aware(row.created_at), "id": row.id, "dto": notification_dto(row)}
                for row in db.scalars(query.order_by(Notification.created_at, Notification.id).limit(100))]


@router.get("/events")
def events(request: Request, account: Verified, db: DB):
    account_id = account.id
    session_id = request.state.browser_session.id
    cursor = utcnow() - timedelta(seconds=2)
    cursor_id = ""
    last_id = request.headers.get("last-event-id")
    if last_id:
        previous = db.get(Notification, last_id)
        if previous and previous.account_id == account_id:
            cursor = aware(previous.created_at)
            cursor_id = previous.id

    async def stream():
        nonlocal cursor, cursor_id
        yield 'event: connected\ndata: {"transport":"sse","reconnect_seconds":60}\nretry: 3000\n\n'
        for _ in range(24):
            if await request.is_disconnected():
                return
            updates = await asyncio.to_thread(event_updates, account_id, session_id, cursor, cursor_id)
            if updates is None:
                yield 'event: session-ended\ndata: {"code":"AUTH_REQUIRED"}\n\n'
                return
            for row in updates:
                cursor, cursor_id = row["timestamp"], row["id"]
                yield f"id: {row['id']}\nevent: notification\ndata: {json.dumps(row['dto'], ensure_ascii=False)}\n\n"
            yield ": heartbeat\n\n"
            await asyncio.sleep(2.5)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"})


@router.get("/quality/summary")
def quality(account: Verified, db: DB):
    from .judge import gateway_status
    from .evaluation_summary import evaluation_summary
    judge = gateway_status()
    require(settings.local_demo and account.email.endswith("@vector.local"), 403, "OPERATOR_REQUIRED", "Раздел доступен оператору локального стенда.")
    attempts = db.scalar(select(func.count()).select_from(AssessmentAttempt))
    return {"environment": "local_demo", "calibration_status": "expert_initial",
        "human_pilot": {"status": "not_measured", "sample_size": 0},
        "evaluation": evaluation_summary(),
        "runtime": {"database": db.bind.dialect.name, "judge": "isolated_runner" if judge.get("available") else "unavailable_fail_closed",
                    "judge_details": judge,
                    "llm_required": False, "mail": "explicit_demo_inbox"},
        "counts": {"candidates": db.scalar(select(func.count()).select_from(Candidate)),
                   "attempts": attempts, "match_runs": db.scalar(select(func.count()).select_from(MatchRun)),
                   "invitations": db.scalar(select(func.count()).select_from(Invitation)),
                   "pending_outbox": db.scalar(select(func.count()).select_from(Outbox).where(Outbox.status == "pending"))},
        "measurement_policy": "Synthetic evaluation is separate from human validity; no invented pilot metrics."}


@router.get("/employer/ats-deliveries")
def ats(account: EmployerUser, db: DB):
    company = company_for(db, account)
    deliveries = db.scalars(select(Delivery).order_by(Delivery.created_at.desc())).all()
    return rows([{"id": row.id, "event_id": row.event_id, "destination": row.destination,
                  "payload": row.payload, "created_at": iso(row.created_at),
                  "source": "signed_webhook" if row.destination == "configured_signed_webhook" else "explicit_demo_ledger"}
                 for row in deliveries if row.payload.get("company_id") == company.id])

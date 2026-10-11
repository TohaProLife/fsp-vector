"""Durable transactional outbox consumer; python -m app.worker.

No user-provided code is executed. The local ATS sink persists idempotently and
never stores candidate contacts. Production transports require explicit adapters.
"""
import argparse
import hashlib
import hmac
import json
import logging
import smtplib
import time
from email.message import EmailMessage
from urllib.parse import urlparse
import httpx
from datetime import timedelta
from sqlalchemy import select
from .common import company_processing_active, iso, private_content_reason
from .config import settings
from .db import SessionLocal
from .models import Candidate, Company, ContactGrant, Delivery, MailMessage, Outbox, utcnow

logger = logging.getLogger("vector.worker")


def deliver_event(db, row):
    existing = db.scalar(select(Delivery).where(Delivery.event_id == row.id))
    if row.kind.startswith("ats.") and not existing:
        candidate = db.scalar(select(Candidate).where(Candidate.id == row.payload.get("candidate_id"))
                              .execution_options(populate_existing=True).with_for_update())
        grant = db.scalar(select(ContactGrant).where(ContactGrant.id == row.payload.get("grant_id")).with_for_update())
        if grant is None or grant.revoked_at is not None:
            row.status, row.completed_at = "cancelled_permission_revoked", utcnow()
            return
        if grant.company_id != row.payload.get("company_id") or grant.candidate_id != row.payload.get("candidate_id"):
            raise ValueError("ATS event/grant scope mismatch")
        company = db.get(Company, grant.company_id)
        if candidate:
            db.info.setdefault("processing_cache", {}).pop(candidate.id, None)
        if private_content_reason(db, candidate, company):
            row.status, row.completed_at = "cancelled_permission_revoked", utcnow()
            return
        if not company_processing_active(db, company, lock=True):
            row.status, row.completed_at = "cancelled_company_unavailable", utcnow()
            return
        payload = {key: value for key, value in row.payload.items()
                   if key in {"company_id", "candidate_id", "invitation_id", "grant_id"}}
        payload = {"kind": row.kind, "event_id": row.id, **payload}
        destination = "demo_ats_ledger"
        if settings.ats_webhook_url:
            url = urlparse(settings.ats_webhook_url)
            if not settings.ats_webhook_secret or url.scheme not in {"http", "https"} or url.username or url.password:
                raise ValueError("ATS signed deployment transport is not configured correctly")
            if url.scheme == "http" and url.hostname not in {"localhost", "127.0.0.1", "::1", "ats-receiver"}:
                raise ValueError("Insecure ATS transport allowed only for the local receiver")
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
            timestamp = str(int(time.time()))
            signature = hmac.new(settings.ats_webhook_secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
            response = httpx.post(settings.ats_webhook_url, content=body, timeout=8,
                follow_redirects=False, headers={"Content-Type":"application/json", "X-Vector-Timestamp":timestamp,
                "X-Vector-Signature":signature, "X-Vector-Event-Id":row.id})
            response.raise_for_status()
            destination = "configured_signed_webhook"
        elif not settings.local_demo:
            raise ValueError("ATS transport not configured")
        db.add(Delivery(event_id=row.id, destination=destination, payload=payload))
    elif row.kind.startswith("email."):
        mail = db.get(MailMessage, row.payload.get("mail_id"))
        if mail is None:
            raise ValueError("Email event references missing message")
        if mail and mail.delivery_status != "delivered":
            if not settings.smtp_host:
                raise ValueError("SMTP transport not configured")
            email = EmailMessage()
            email["From"], email["To"], email["Subject"] = settings.smtp_sender, mail.to, mail.subject
            email["Message-ID"] = f"<{mail.id}@vector.local>"
            email.set_content(mail.body)
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
                smtp.send_message(email)
            mail.delivery_status, mail.delivered_at, mail.delivery_error = "delivered", utcnow(), None
    elif row.kind != "notification" and not row.kind.startswith("ats."):
        raise ValueError(f"Unsupported adapter: {row.kind}")
    row.status, row.completed_at, row.error = "completed", utcnow(), None


def consume_once(limit=50):
    completed = 0
    # A claimed event owns its own transaction. Permission locks are held only
    # through that event's transport, never through unrelated later timeouts.
    for _ in range(limit):
        with SessionLocal() as db:
            row = db.scalar(select(Outbox).where(Outbox.status == "pending", Outbox.available_at <= utcnow())
                        .order_by(Outbox.created_at).limit(1).with_for_update(skip_locked=True))
            if row is None:
                break
            row.attempts += 1
            try:
                # An adapter failure cannot poison the remaining DB transaction.
                with db.begin_nested():
                    deliver_event(db, row)
                if row.status == "completed":
                    completed += 1
            except Exception as exc:
                row.error = str(exc)[:500]
                if row.kind.startswith("email."):
                    mail = db.get(MailMessage, row.payload.get("mail_id"))
                    if mail:
                        mail.delivery_status, mail.delivery_error = "retry_pending", row.error
                row.available_at = utcnow() + timedelta(seconds=min(300, 2 ** row.attempts))
                if row.attempts >= 5:
                    row.status = "failed"
                    if row.kind.startswith("email.") and mail:
                        mail.delivery_status = "failed"
                logger.warning("Outbox retry %s: %s", row.id, type(exc).__name__)
            db.commit()
    return completed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    next_schedule = 0
    while True:
        if time.monotonic() >= next_schedule:
            try:
                from .practice import schedule_weekly_practice
                with SessionLocal() as db:
                    schedule_weekly_practice(db)
                    db.commit()
            except Exception as exc:
                logger.warning("Weekly practice scheduling unavailable: %s", type(exc).__name__)
            next_schedule = time.monotonic() + 60
        count = consume_once()
        if count:
            logger.info("Completed %s events", count)
        if args.once:
            break
        time.sleep(1)


if __name__ == "__main__":
    main()

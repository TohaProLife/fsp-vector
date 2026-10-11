"""Persisted weekly, candidate-owned objective practice and internal cadence."""
import secrets
from datetime import datetime, timedelta, timezone
from sqlalchemy import exists, select
from .common import audit, aware, emit, iso, processing_active, require
from .config import settings
from .models import Account, AuditEvent, Candidate, Challenge, ChallengeSubmission, Consent, utcnow


def week_window(now=None):
    now = aware(now or utcnow())
    monday = datetime(now.year, now.month, now.day, tzinfo=timezone.utc) - timedelta(days=now.weekday())
    year, week, _ = now.isocalendar()
    return f"{year}-W{week:02}", monday, monday + timedelta(days=7)


def challenge_visible(row, account, candidate=None):
    assigned = row.data.get("assigned_candidate_id")
    return not assigned or bool(account.role == "candidate" and candidate and candidate.id == assigned)


def latest_submission(db, challenge, candidate):
    return db.scalar(select(ChallengeSubmission).where(ChallengeSubmission.challenge_id == challenge.id,
        ChallengeSubmission.candidate_id == candidate.id).order_by(ChallengeSubmission.created_at.desc()).limit(1))


def submission_dto(row):
    return {"id": row.id, "challenge_id": row.challenge_id, "result": row.result,
            "created_at": iso(row.created_at)} if row else None


def retry_at(submission):
    if submission and not submission.result.get("passed") and submission.result.get("status") in {"graded", "failed"}:
        return aware(submission.created_at) + timedelta(hours=24)
    return None


def practice_notifications_allowed(db, account):
    consent = db.scalar(select(Consent).where(Consent.account_id == account.id,
        Consent.purpose == "practice").order_by(Consent.created_at.desc()).limit(1))
    return bool(consent.granted if consent else settings.local_demo)


def ensure_weekly_challenge(db, candidate, account, now=None, notify=True):
    """Caller holds the candidate row lock, shared with consent withdrawal."""
    week_id, opened, next_week = week_window(now)
    specialization = candidate.specialization or "backend"
    grade = candidate.confirmed_grade or candidate.declared_grade or "junior"
    row = db.scalar(select(Challenge).where(
        Challenge.data["assigned_candidate_id"].as_string() == candidate.id,
        Challenge.data["recurrence_week"].as_string() == week_id,
        Challenge.data["specialization"].as_string() == specialization,
        Challenge.data["grade"].as_string() == grade))
    if row is None:
        from .engines.assessment import catalog, generate_assessment
        taxonomy = catalog()
        spec = next((item for item in taxonomy["specializations"] if item["id"] == specialization), None)
        require(spec is not None, 503, "PRACTICE_UNAVAILABLE", "Практика для этой специализации пока не доступна.")
        form = generate_assessment(specialization, grade, stack=spec["default_contexts"], seed=secrets.randbits(62))
        practical = sorted((item for item in form["private_payload"]["items"]
            if item.get("slot") in {"practice", "mutation"}), key=lambda item: item["competency"])
        require(practical, 503, "PRACTICE_UNAVAILABLE", "Для этой специализации ещё нет объективной короткой задачи.")
        # Rotate measured competencies, while each week's generated inputs differ.
        item = practical[(opened.toordinal() // 7) % len(practical)]
        public = next(value for value in form["items"] if value["id"] == item["id"])
        skills = public.get("evidence_skills") or [public.get("competency_label", "Практика")]
        row = Challenge(company_id=None, data={"title": f"Практика {week_id}: {public['title']}",
            "description": public["prompt"], "specialization": specialization, "grade": grade,
            "skill": skills[0], "public_task": public, "assigned_candidate_id": candidate.id,
            "recurrence_week": week_id, "opens_at": iso(opened), "next_week_at": iso(next_week),
            "estimated_minutes": 10, "scope": "weekly_objective_practice",
            "blueprint_version": form["blueprint_version"]},
            rubric={"kind": "objective_declarative", "item": item})
        db.add(row)
        db.flush()
        audit(db, account, "practice.weekly_created", row.id, {"week_id": week_id, "category_changed": False})
    if notify and practice_notifications_allowed(db, account):
        sent = db.scalar(select(AuditEvent.id).where(AuditEvent.account_id == account.id,
            AuditEvent.action == "practice.weekly_notified", AuditEvent.data["week_id"].as_string() == week_id))
        if not sent:
            emit(db, account.id, "practice.weekly", "Новая короткая практика недели",
                 {"challenge_id": row.id, "week_id": week_id, "href": "/workspace/practice"})
            audit(db, account, "practice.weekly_notified", row.id, {"week_id": week_id})
    return row


def schedule_weekly_practice(db, limit=10, now=None):
    week_id, _, _ = week_window(now)
    latest_processing = select(Consent.granted).where(Consent.account_id == Candidate.account_id,
        Consent.purpose == "processing").order_by(Consent.created_at.desc()).limit(1).scalar_subquery()
    latest_opt_in = select(Consent.granted).where(Consent.account_id == Candidate.account_id,
        Consent.purpose == "practice").order_by(Consent.created_at.desc()).limit(1).scalar_subquery()
    already = exists(select(AuditEvent.id).where(AuditEvent.account_id == Candidate.account_id,
        AuditEvent.action == "practice.weekly_notified", AuditEvent.data["week_id"].as_string() == week_id))
    query = select(Candidate).join(Account, Account.id == Candidate.account_id).where(
        Account.email_verified.is_(True), latest_processing.is_(True), ~already)
    query = query.where(latest_opt_in.is_not(False) if settings.local_demo else latest_opt_in.is_(True))
    candidates = db.scalars(query.order_by(Candidate.created_at).limit(limit)
        .with_for_update(of=Candidate, skip_locked=True)).all()
    scheduled = 0
    for candidate in candidates:
        db.info.setdefault("processing_cache", {}).pop(candidate.id, None)
        if processing_active(db, candidate):
            ensure_weekly_challenge(db, candidate, db.get(Account, candidate.account_id), now=now)
            scheduled += 1
    return scheduled

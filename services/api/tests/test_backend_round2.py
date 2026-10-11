"""Regression audit for concrete round-two domain/privacy/readiness gaps."""
import json
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from app.common import Problem, aware
from app.db import Base
from app.models import AssessmentAttempt, AuditEvent, BrowserSession, Candidate, Challenge, ChallengeSubmission, Consent, MailMessage, Notification, Outbox, utcnow
from test_domain_api import database, logged, confirm_fixture, create_attempt, invite, need_body, reference_answers


def test_survey_history_keeps_versioned_answers_and_is_owned(database):
    candidate, other = logged(), logged("other@vector.local")
    first = {"industry": "ИТ", "specialization": "backend", "grade": "junior", "stack": ["Python", "SQL"]}
    second = {**first, "grade": "middle", "work_format": "hybrid"}
    assert candidate.post("/api/v1/candidate/survey", json=first).status_code == 200
    assert candidate.post("/api/v1/candidate/survey", json=second).status_code == 200
    history = candidate.get("/api/v1/candidate/survey-history").json()
    assert history["total"] == 2
    assert [item["answers"]["grade"] for item in history["items"]] == ["middle", "junior"]
    assert all(item["taxonomy_version"] and item["snapshot_available"] for item in history["items"])
    assert other.get("/api/v1/candidate/survey-history").json()["items"] == []
    assert candidate.get("/api/v1/candidate/profile").json()["survey_history"] == history["items"]
    with database() as db:
        db.add(AuditEvent(account_id="account-1", action="survey.completed", data={}))
        db.commit()
    legacy = candidate.get("/api/v1/candidate/survey-history").json()["items"][0]
    assert not legacy["snapshot_available"] and legacy["answers"] is None


def test_processing_withdrawal_hides_historical_application_and_practice_profile(database):
    confirm_fixture(database)
    candidate, employer = logged(), logged("employer@vector.local")
    vacancy = employer.post("/api/v1/vacancies", json=need_body()).json()
    assert candidate.post(f"/api/v1/vacancies/{vacancy['id']}/apply", json={"consent_contacts": True}).status_code == 201
    challenge = employer.post("/api/v1/challenges", json={"title": "Контракт API", "description": "Опишите идемпотентность API",
        "specialization": "backend", "skill": "API", "public_task": {"type": "text", "prompt": "Как хранить event_id?"}}).json()
    candidate.post(f"/api/v1/challenges/{challenge['id']}/submit", json={"answer": "Уникальность event_id и транзакция"})
    assert employer.get("/api/v1/applications").json()["items"][0]["candidate"]["evidence"]
    assert candidate.post("/api/v1/candidate/consents", json={"purpose": "processing", "granted": False}).status_code == 200
    projections = [employer.get("/api/v1/applications").json()["items"][0]["candidate"],
        employer.get(f"/api/v1/challenges/{challenge['id']}/submissions").json()["items"][0]["candidate"]]
    for profile in projections:
        assert not profile["contact_authorized"] and not profile["profile_available"]
        assert not {"contacts", "evidence", "fsp", "title", "skills"} & set(profile)
        assert "Private Person" not in json.dumps(profile)


def test_blocked_company_cannot_read_application_evidence_even_if_card_remains_published(database):
    confirm_fixture(database)
    candidate, employer = logged(), logged("employer@vector.local")
    vacancy = employer.post("/api/v1/vacancies", json=need_body()).json()
    candidate.post(f"/api/v1/vacancies/{vacancy['id']}/apply", json={"consent_contacts": True})
    candidate.post("/api/v1/candidate/companies/company-3/block")
    profile = employer.get("/api/v1/applications").json()["items"][0]["candidate"]
    assert "evidence" not in profile and "contacts" not in profile
    assert candidate.get("/api/v1/candidate/profile").json()["published"]


def test_refine_uses_saved_need_snapshot_after_need_edit(database):
    confirm_fixture(database)
    employer = logged("employer@vector.local")
    need = employer.post("/api/v1/employer/needs", json=need_body()).json()
    parent = employer.post("/api/v1/employer/matches", json={"need_id": need["id"]}).json()
    assert parent["total"] == 1
    assert employer.patch(f"/api/v1/employer/needs/{need['id']}", json={"required_skills": ["React"]}).status_code == 200
    child = employer.post(f"/api/v1/employer/matches/{parent['id']}/refine", json={"filters": {"work_format": "remote"}}).json()
    assert child["need"] == parent["need"] and child["total"] == 1
    fresh = employer.post("/api/v1/employer/matches", json={"need_id": need["id"]}).json()
    assert fresh["need"]["required_skills"] == ["React"] and fresh["total"] == 0


def test_expiration_is_deadline_not_time_profile_was_reopened(database):
    candidate = logged()
    attempt = create_attempt(candidate)
    expired = utcnow() - timedelta(days=3)
    with database() as db:
        db.get(AssessmentAttempt, attempt["id"]).expires_at = expired
        db.commit()
    assert candidate.get(f"/api/v1/assessments/{attempt['id']}").json()["status"] == "expired"
    with database() as db:
        assert aware(db.get(AssessmentAttempt, attempt["id"]).finished_at) == expired
    assert candidate.post("/api/v1/assessments/start", json={"specialization": "backend", "grade": "junior", "stack": ["Python"]}).status_code == 201


def test_viewed_is_candidate_owned_idempotent_and_does_not_change_pending_state(database):
    confirm_fixture(database)
    candidate, employer, other = logged(), logged("employer@vector.local"), logged("other@vector.local")
    invitation = invite(employer).json()
    path = f"/api/v1/invitations/{invitation['id']}"
    assert employer.get(path).json()["viewed_at"] is None
    assert other.get(path).status_code == 404
    first, repeated = candidate.get(path).json(), candidate.get(path).json()
    assert first["viewed_at"] and first["viewed_at"] == repeated["viewed_at"]
    assert first["status"] == "pending"
    assert employer.get(path).json()["viewed_at"] == first["viewed_at"]
    with database() as db:
        assert db.scalar(select(func.count()).select_from(Notification).where(Notification.kind == "invitation.viewed")) == 1


def test_readiness_rejects_missing_columns_and_absent_or_wrong_migration(database):
    from app.readiness import schema_readiness
    with database() as db:
        with db.bind.connect() as connection:
            assert schema_readiness(connection, require_migration=False)["schema"]
            with pytest.raises(Problem) as missing_revision:
                schema_readiness(connection, require_migration=True)
            assert missing_revision.value.code == "SCHEMA_NOT_READY"
            connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
            connection.execute(text("INSERT INTO alembic_version VALUES ('wrong_revision')"))
            with pytest.raises(Problem) as wrong_revision:
                schema_readiness(connection)
            assert wrong_revision.value.status == 503
            connection.execute(text("UPDATE alembic_version SET version_num='0001'"))
            assert schema_readiness(connection)["migration"] == "checked"
            connection.execute(text("ALTER TABLE candidates DROP COLUMN bio"))
            with pytest.raises(Problem) as missing_column:
                schema_readiness(connection, require_migration=False)
            assert missing_column.value.code == "SCHEMA_NOT_READY"
    empty = create_engine("sqlite://")
    with empty.connect() as connection:
        with pytest.raises(Problem) as missing_tables:
            schema_readiness(connection, require_migration=False)
        assert missing_tables.value.code == "SCHEMA_NOT_READY"
    empty.dispose()


def test_production_guard_rejects_insecure_runtime_without_printing_database_secret():
    from app.config import settings, validate_runtime_configuration
    unsafe = replace(settings, local_demo=False, auto_seed=True, auto_create_schema=True,
        cookie_secure=False, database_url="sqlite:///SECRET_DATABASE_MARKER", smtp_host="", frontend_url="http://localhost:3000")
    with pytest.raises(RuntimeError) as failure:
        validate_runtime_configuration(unsafe)
    assert "SECRET_DATABASE_MARKER" not in str(failure.value)
    assert "COOKIE_SECURE" in str(failure.value) and "AUTO_SEED" in str(failure.value)
    safe = replace(unsafe, auto_seed=False, auto_create_schema=False, cookie_secure=True,
        database_url="postgresql+psycopg://unused:SECRET@db/vector", smtp_host="smtp", frontend_url="https://vector.example")
    validate_runtime_configuration(safe)
    with pytest.raises(RuntimeError):
        validate_runtime_configuration(replace(settings, local_demo=True, frontend_url="https://public.example"))


def test_production_blocks_existing_demo_session_and_published_password(database, monkeypatch):
    import app.auth as auth
    client = logged()
    monkeypatch.setattr(auth, "settings", replace(auth.settings, local_demo=False))
    assert client.get("/api/v1/auth/me").status_code == 401
    assert TestClient(__import__("app.main", fromlist=["app"]).app).post("/api/v1/auth/login",
        json={"email": "employer@vector.local", "password": "VectorDemo2026!"}).status_code == 401
    anonymous = TestClient(__import__("app.main", fromlist=["app"]).app)
    assert anonymous.post("/api/v1/auth/register", json={"name": "New user", "email": "test@example.invalid",
        "password": "VectorDemo2026!", "role": "candidate", "consent_processing": True}).status_code == 400
    assert anonymous.post("/api/v1/auth/register", json={"name": "New user", "email": "test@vector.local",
        "password": "DifferentProdPassword2026!", "role": "candidate", "consent_processing": True}).status_code == 400


def test_need_practice_snapshot_ownership_and_non_certification(database):
    from evaluation.reference_solvers import reference_answer
    confirm_fixture(database)
    candidate, employer, outsider = logged(), logged("employer@vector.local"), logged("employer2@vector.local")
    need = employer.post("/api/v1/employer/needs", json=need_body()).json()
    assert outsider.get(f"/api/v1/employer/needs/{need['id']}/assessment-blueprint").status_code == 404
    blueprint = employer.get(f"/api/v1/employer/needs/{need['id']}/assessment-blueprint").json()
    assert blueprint["need_snapshot_sha256"] and blueprint["unmeasured_skills"]
    invitation = invite(employer, need_id=need["id"]).json()
    assert employer.patch(f"/api/v1/employer/needs/{need['id']}", json={"required_skills": ["Docker"]}).status_code == 200
    assert logged("other@vector.local").post("/api/v1/assessments/need-start", json={"invitation_id": invitation["id"]}).status_code == 404
    response = candidate.post("/api/v1/assessments/need-start", json={"invitation_id": invitation["id"]})
    assert response.status_code == 201, response.text
    attempt = response.json()
    assert attempt["scope"] == "employer_need_practice" and not attempt["certifies_global_category"]
    assert attempt["context"]["need_snapshot_sha256"] == blueprint["need_snapshot_sha256"]
    assert "_oracle" not in json.dumps(attempt) and "_private" not in json.dumps(attempt)
    before = candidate.get("/api/v1/candidate/profile").json()
    answers = {item["id"]: reference_answer(item) for item in attempt["items"]}
    completed = candidate.post(f"/api/v1/assessments/{attempt['id']}/submit", json={"answers": answers}).json()
    assert completed["result"]["passed"] and not completed["result"]["category_changed"]
    assert not completed["result"]["certifies_global_category"] and completed["result"]["confirmed_grade"] is None
    after = candidate.get("/api/v1/candidate/profile").json()
    for field in ["confirmed_grade", "confirmed_categories", "score", "assessment_at"]:
        assert after[field] == before[field]
    replayed = candidate.post(f"/api/v1/assessments/{attempt['id']}/submit", json={"answers": {}})
    assert replayed.status_code == 200 and replayed.json()["result"] == completed["result"]
    with database() as db:
        notices = db.scalars(select(Notification).where(Notification.account_id == "account-1",
            Notification.kind == "assessment.completed", Notification.data["attempt_id"].as_string() == attempt["id"])).all()
        assert len(notices) == 1 and notices[0].title == "Результат практики по потребности готов"
        assert notices[0].data == {"attempt_id": attempt["id"], "passed": True, "demo": False}
        assert db.scalar(select(func.count()).select_from(Outbox).where(Outbox.kind == "notification",
            Outbox.payload["notification_id"].as_string() == notices[0].id)) == 1
    observations = [item for item in after["evidence"] if item["source"] == "NEED_PRACTICE_OBSERVED"]
    assert observations and all(not item["scope"]["global_grade"] for item in observations)
    other_profile = outsider.get("/api/v1/employer/candidates/candidate-1").json()
    assert not any(item["source"] == "NEED_PRACTICE_OBSERVED" for item in other_profile["evidence"])
    assert candidate.post("/api/v1/assessments/need-start", json={"invitation_id": invitation["id"]}).status_code == 409
    assert all(item["allowed"] for item in candidate.get("/api/v1/assessments/availability").json()["items"])


def test_need_practice_does_not_open_contacts_and_unpublished_job_is_not_accessible(database):
    employer, candidate = logged("employer@vector.local"), logged()
    vacancy = employer.post("/api/v1/vacancies", json=need_body()).json()
    path = "/api/v1/assessments/need-start"
    assert candidate.post(path, json={"vacancy_id": vacancy["id"], "need_id": "private"}).status_code == 422
    assert candidate.post(path, json={"vacancy_id": vacancy["id"], "invitation_id": "anything"}).status_code == 400
    employer.patch(f"/api/v1/vacancies/{vacancy['id']}", json={"published": False})
    assert candidate.post(path, json={"vacancy_id": vacancy["id"]}).status_code == 404
    employer.patch(f"/api/v1/vacancies/{vacancy['id']}", json={"published": True})
    attempt = candidate.post(path, json={"vacancy_id": vacancy["id"]}).json()
    result = candidate.post(f"/api/v1/assessments/{attempt['id']}/submit", json={"answers": reference_answers(database, attempt["id"])}).json()["result"]
    assert result["passed"] and result["confirmed_grade"] is None
    assert candidate.get("/api/v1/candidate/profile").json()["contact_grants"] == []
    assert employer.get("/api/v1/employer/candidates/candidate-1").status_code == 404


def test_weekly_practice_has_real_results_ownership_cooldown_and_no_replay_freshening(database):
    from evaluation.reference_solvers import reference_answer
    candidate, other, employer = logged(), logged("other@vector.local"), logged("employer@vector.local")
    first = candidate.get("/api/v1/challenges/weekly").json()
    assert first["policy"]["recurrence"] == "weekly" and not first["completed"]
    challenge = first["challenge"]
    repeated = candidate.get("/api/v1/challenges/weekly").json()
    assert repeated["challenge"]["id"] == challenge["id"]
    assert other.get(f"/api/v1/challenges/{challenge['id']}").status_code == 404
    assert employer.get(f"/api/v1/challenges/{challenge['id']}").status_code == 404
    path = f"/api/v1/challenges/{challenge['id']}/submit"
    assert other.post(path, json={"answer": None}).status_code == 404
    failed = candidate.post(path, json={"answer": None}).json()
    assert failed["result"]["score"] == 0 and not failed["result"]["passed"]
    answer = reference_answer(challenge["public_task"])
    assert candidate.post(path, json={"answer": answer}).status_code == 409
    assert candidate.get("/api/v1/challenges/weekly").json()["retry_at"]
    with database() as db:
        db.get(ChallengeSubmission, failed["id"]).created_at = utcnow() - timedelta(hours=24, seconds=1)
        db.commit()
    passed = candidate.post(path, json={"answer": answer}).json()
    assert passed["result"]["passed"] and not passed["result"]["category_changed"]
    before = candidate.get("/api/v1/candidate/profile").json()["evidence"]
    replay = candidate.post(path, json={"answer": None}).json()
    assert replay["id"] == passed["id"] and replay["replayed"]
    assert candidate.get("/api/v1/candidate/profile").json()["evidence"] == before
    assert candidate.get("/api/v1/candidate/profile").json()["confirmed_grade"] is None
    assert candidate.get("/api/v1/challenges/weekly").json()["completed"]
    with database() as db:
        assert db.scalar(select(func.count()).select_from(Notification).where(Notification.kind == "practice.weekly")) == 1


def test_weekly_recurrence_creates_new_persisted_inputs_and_background_opt_in_is_required(database, monkeypatch):
    import app.practice as practice
    candidate = logged()
    first = candidate.get("/api/v1/challenges/weekly").json()
    now = utcnow()
    monkeypatch.setattr(practice, "utcnow", lambda: now + timedelta(days=7))
    second = candidate.get("/api/v1/challenges/weekly").json()
    assert first["week_id"] != second["week_id"]
    assert first["challenge"]["id"] != second["challenge"]["id"]
    assert first["challenge"]["public_task"] != second["challenge"]["public_task"]
    monkeypatch.setattr(practice, "settings", replace(practice.settings, local_demo=False))
    with database() as db:
        assert practice.schedule_weekly_practice(db, now=now + timedelta(days=14)) == 0
    candidate.post("/api/v1/candidate/consents", json={"purpose": "practice", "granted": True})
    with database() as db:
        assert practice.schedule_weekly_practice(db, now=now + timedelta(days=14)) == 1
        db.commit()
    with database() as db:
        assert practice.schedule_weekly_practice(db, now=now + timedelta(days=14)) == 0
    candidate.post("/api/v1/candidate/consents", json={"purpose": "practice", "granted": False})
    with database() as db:
        assert practice.schedule_weekly_practice(db, now=now + timedelta(days=21)) == 0


def test_formal_availability_reports_cooldown_but_need_practice_is_not_category_history(database):
    candidate = logged()
    attempt = create_attempt(candidate)
    candidate.post(f"/api/v1/assessments/{attempt['id']}/submit", json={"answers": reference_answers(database, attempt["id"])})
    availability = candidate.get("/api/v1/assessments/availability?specialization=backend").json()
    grades = {item["grade"]: item for item in availability["items"]}
    assert not grades["junior"]["allowed"] and grades["junior"]["reason"] == "same_grade_retest_7_days"
    assert not grades["middle"]["allowed"] and grades["middle"]["reason"] == "grade_change_90_days"
    assert all(item["next_allowed_at"] for item in grades.values())
    assert availability["active_attempt"] is None and availability["server_time"]


def test_sse_reader_rechecks_session_processing_and_does_not_skip_equal_timestamp_events(database):
    from app.auth import digest
    from app.platform import event_updates
    candidate = logged()
    created = utcnow()
    with database() as db:
        session_id = db.scalar(select(BrowserSession.id).where(
            BrowserSession.token_hash == digest(candidate.cookies.get("vector_session"))))
        for index in range(105):
            db.add(Notification(id=f"event-{index:03}", account_id="account-1", kind="audit",
                title="Owned event", data={}, created_at=created))
        db.add(Notification(id="other-event", account_id="account-2", kind="audit", title="Other account", data={}, created_at=created))
        db.commit()
    first = event_updates("account-1", session_id, created - timedelta(seconds=1))
    second = event_updates("account-1", session_id, first[-1]["timestamp"], first[-1]["id"])
    assert len(first) == 100 and len(second) == 5
    assert all(item["id"] != "other-event" for item in first + second)
    assert len({item["id"] for item in first + second}) == 105
    assert candidate.post("/api/v1/auth/consents", json={"consent_processing": False}).status_code == 200
    assert event_updates("account-1", session_id, created - timedelta(seconds=1)) is None
    assert candidate.post("/api/v1/auth/consents", json={"consent_processing": True}).status_code == 200
    assert candidate.post("/api/v1/auth/logout").status_code == 200
    assert event_updates("account-1", session_id, created - timedelta(seconds=1)) is None


def test_practice_consent_exposes_effective_demo_default_and_persisted_opt_out(database):
    candidate = logged()
    initial = candidate.get("/api/v1/candidate/consents").json()
    assert "practice" not in initial["current"] and initial["effective_practice_notifications"]
    changed = candidate.post("/api/v1/candidate/consents", json={"purpose": "practice", "granted": False}).json()
    assert not changed["effective_practice_notifications"] and changed["current"]["practice"] is False


def test_processing_withdrawal_closes_accepted_invitation_messaging(database):
    confirm_fixture(database)
    employer, candidate = logged("employer@vector.local"), logged()
    invitation = invite(employer).json()
    candidate.post(f"/api/v1/invitations/{invitation['id']}/accept")
    path = f"/api/v1/invitations/{invitation['id']}/messages"
    assert employer.post(path, json={"text": "Обсудим формат работы?"}).status_code == 201
    candidate.post("/api/v1/auth/consents", json={"consent_processing": False})
    assert employer.post(path, json={"text": "Новое сообщение после отзыва"}).status_code == 409
    assert len(employer.get(f"/api/v1/invitations/{invitation['id']}").json()["messages"]) == 1


def test_exhausted_email_outbox_does_not_keep_claiming_future_retry(database, monkeypatch):
    import app.auth as auth
    import app.worker as worker
    from app.main import app
    configured = replace(auth.settings, smtp_host="127.0.0.1", smtp_port=1025)
    monkeypatch.setattr(auth, "settings", configured)
    monkeypatch.setattr(worker, "settings", configured)
    response = TestClient(app).post("/api/v1/auth/register", json={"name": "Terminal SMTP test", "email": "failed@example.invalid",
        "password": "VectorDemo2026!", "role": "candidate", "consent_processing": True})
    assert response.status_code == 201
    def unavailable(*args, **kwargs):
        raise OSError("synthetic unavailable transport")
    monkeypatch.setattr(worker.smtplib, "SMTP", unavailable)
    for _ in range(5):
        with database() as db:
            event = db.scalar(select(Outbox).where(Outbox.kind == "email.verification"))
            event.available_at = utcnow() - timedelta(seconds=1)
            db.commit()
        worker.consume_once()
    with database() as db:
        event = db.scalar(select(Outbox).where(Outbox.kind == "email.verification"))
        mail = db.scalar(select(MailMessage).where(MailMessage.to == "failed@example.invalid"))
        assert event.status == "failed" and event.attempts == 5
        assert mail.delivery_status == "failed" and mail.delivered_at is None
    assert worker.consume_once() == 0


def test_matching_uses_only_own_company_need_practice_without_pii(database, monkeypatch):
    from evaluation.reference_solvers import reference_answer
    import app.engines.matching as matching
    confirm_fixture(database)
    with database() as db:
        db.get(Candidate, "candidate-1").assessment_at = utcnow() - timedelta(days=200)
        db.commit()
    candidate, company_a, company_b = logged(), logged("employer@vector.local"), logged("employer2@vector.local")
    need_a = company_a.post("/api/v1/employer/needs", json=need_body(skills=["API"])).json()
    need_b = company_b.post("/api/v1/employer/needs", json=need_body(skills=["API"])).json()
    invitation = invite(company_a, need_id=need_a["id"]).json()
    candidate.post(f"/api/v1/invitations/{invitation['id']}/accept")
    original = matching.rank_candidates
    def capture(need, candidates, **kwargs):
        payload = json.dumps(candidates)
        assert "PRIVATE-PHONE" not in payload and "Private Person" not in payload
        assert all("contacts" not in item and "bio" not in item and "name" not in item for item in candidates)
        return original(need, candidates, **kwargs)
    monkeypatch.setattr(matching, "rank_candidates", capture)
    def match(client, need):
        response = client.post("/api/v1/employer/matches", json={"need_id": need["id"]})
        assert response.status_code == 201, response.text
        return response.json()["items"][0]
    before_a, before_b = match(company_a, need_a), match(company_b, need_b)
    attempt = candidate.post("/api/v1/assessments/need-start", json={"invitation_id": invitation["id"]}).json()
    completed = candidate.post(f"/api/v1/assessments/{attempt['id']}/submit", json={
        "answers": {item["id"]: reference_answer(item) for item in attempt["items"]}})
    assert completed.json()["result"]["passed"]
    after_a, after_b = match(company_a, need_a), match(company_b, need_b)
    assert after_a["breakdown"]["freshness"]["points"] > before_a["breakdown"]["freshness"]["points"]
    assert after_a["breakdown"]["freshness"]["points"] - before_a["breakdown"]["freshness"]["points"] <= 1.25
    assert after_b["breakdown"]["freshness"] == before_b["breakdown"]["freshness"]
    assert after_b["score"] == before_b["score"]


def test_weekly_rotation_covers_all_practical_competencies_in_every_specialization(database):
    from app.engines.assessment import catalog
    from app.models import Account
    from app.practice import ensure_weekly_challenge
    first_week = datetime(2026, 10, 5, tzinfo=timezone.utc)
    for index, spec in enumerate(catalog()["specializations"]):
        seen, slots = set(), set()
        with database() as db:
            candidate = db.get(Candidate, "candidate-1")
            candidate.specialization, candidate.declared_grade = spec["id"], "junior"
            account = db.get(Account, candidate.account_id)
            for week in range(4):
                task = ensure_weekly_challenge(db, candidate, account,
                    now=first_week + timedelta(weeks=index * 4 + week), notify=False)
                seen.add(task.rubric["item"]["competency"])
                slots.add(task.rubric["item"]["slot"])
            db.commit()
        assert seen == {item["id"] for item in spec["competencies"]}
        assert slots == {"practice", "mutation"}


def test_fsp_filter_includes_sync_ok_without_converting_demo_provenance_or_bypassing_gates(database):
    confirm_fixture(database)
    with database() as db:
        linked = {"fsp_id": "FSP-TEST-OWNED", "status": "sync_ok", "source": "FSP_DEMO_CONFIRMED",
            "is_demo": True, "achievements": [{"title": "Synthetic result", "source": "FSP_DEMO_CONFIRMED", "is_demo": True}]}
        db.get(Candidate, "candidate-1").fsp = linked
        # Linked IDs never substitute for category or processing permission.
        unconfirmed = db.get(Candidate, "candidate-2")
        unconfirmed.fsp, unconfirmed.published = linked, True
        db.commit()
    employer, candidate = logged("employer@vector.local"), logged()
    filtered = employer.get("/api/v1/employer/candidates?fsp_only=true").json()
    assert filtered["total"] == 1 and filtered["items"][0]["id"] == "candidate-1"
    fsp = filtered["items"][0]["fsp"]
    assert fsp["status"] == "sync_ok" and fsp["source"] == "FSP_DEMO_CONFIRMED" and fsp["is_demo"] is True
    assert all(item["source"] == "FSP_DEMO_CONFIRMED" and item["is_demo"] for item in fsp["achievements"])
    assert "contacts" not in filtered["items"][0]
    assert candidate.get("/api/v1/employer/candidates?fsp_only=true").status_code == 403
    candidate.post("/api/v1/candidate/consents", json={"purpose": "fsp", "granted": False})
    assert employer.get("/api/v1/employer/candidates?fsp_only=true").json()["total"] == 0
    assert employer.get("/api/v1/employer/candidates").json()["total"] == 1
    with database() as db:
        other = db.get(Candidate, "candidate-2")
        other.confirmed_grade = "junior"
        db.add(Consent(account_id=other.account_id, purpose="processing", granted=False))
        db.commit()
    assert employer.get("/api/v1/employer/candidates?fsp_only=true").json()["total"] == 0


@pytest.mark.parametrize("internal", ["http://identity:8080/realms/vector", "https://user:password@identity/realms/vector",
    "https://identity/realms/vector?token=private", "https://identity/realms/vector#fragment"])
def test_production_oidc_internal_transport_fails_closed_before_discovery(monkeypatch, internal):
    import app.oidc as oidc
    monkeypatch.setattr(oidc, "settings", replace(oidc.settings, local_demo=False, frontend_url="https://vector.example"))
    monkeypatch.setattr(oidc, "config", replace(oidc.config, issuer="https://identity.example/realms/vector",
        client_secret="synthetic-confidential-test-only", redirect_uri="https://vector.example/api/v1/auth/oidc/callback",
        internal_issuer=internal))
    def never_request(*args, **kwargs):
        raise AssertionError("Unsafe internal transport must fail before any provider request")
    monkeypatch.setattr(oidc.httpx, "Client", never_request)
    assert "OIDC_INTERNAL_ISSUER must use trusted HTTPS transport in production" in oidc.production_config_errors()
    with pytest.raises(Problem) as failure:
        oidc.discovery()
    assert failure.value.status == 503 and failure.value.code == "OIDC_UNSAFE_CONFIG"


def test_production_oidc_https_internal_and_local_demo_http_transport_are_explicit(monkeypatch):
    import app.oidc as oidc
    external = "https://identity.example/realms/vector"
    monkeypatch.setattr(oidc, "settings", replace(oidc.settings, local_demo=False, frontend_url="https://vector.example"))
    monkeypatch.setattr(oidc, "config", replace(oidc.config, issuer=external, client_secret="synthetic-test-only",
        redirect_uri="https://vector.example/api/v1/auth/oidc/callback", internal_issuer="https://identity.internal/realms/vector"))
    assert oidc.production_config_errors() == []
    assert oidc.transport_url(external + "/protocol/openid-connect/token") == "https://identity.internal/realms/vector/protocol/openid-connect/token"
    monkeypatch.setattr(oidc, "settings", replace(oidc.settings, local_demo=True))
    monkeypatch.setattr(oidc, "config", replace(oidc.config, internal_issuer="http://identity:8080/realms/vector"))
    assert oidc.production_config_errors() == []


def test_weekly_assignment_changes_with_route_preserves_old_solution_and_notifies_once(database):
    from evaluation.reference_solvers import reference_answer
    from app.practice import schedule_weekly_practice
    with database() as db:
        participant = db.get(Candidate, "candidate-1")
        participant.specialization, participant.declared_grade, participant.survey = None, "intern", {}
        assert schedule_weekly_practice(db, limit=1) == 1
        db.commit()
    candidate = logged()
    before = candidate.get("/api/v1/challenges/weekly").json()
    old = before["challenge"]
    assert old["specialization"] == "backend" and old["grade"] == "intern"
    solved = candidate.post(f"/api/v1/challenges/{old['id']}/submit", json={"answer": reference_answer(old["public_task"])})
    assert solved.status_code == 201 and solved.json()["result"]["passed"]
    with database() as db:
        old_data, old_rubric = deepcopy(db.get(Challenge, old["id"]).data), deepcopy(db.get(Challenge, old["id"]).rubric)
        old_result = deepcopy(db.get(ChallengeSubmission, solved.json()["id"]).result)
    survey = {"industry": "ИТ", "specialization": "frontend", "grade": "middle", "stack": ["TypeScript", "React"]}
    assert candidate.post("/api/v1/candidate/survey", json=survey).status_code == 200
    changed = candidate.get("/api/v1/challenges/weekly").json()
    assert changed["challenge"]["id"] != old["id"]
    assert changed["challenge"]["specialization"] == "frontend" and changed["challenge"]["grade"] == "middle"
    assert changed["submission"] is None and not changed["completed"]
    # A formal confirmation of the same effective route must reuse its task.
    attempt_response = candidate.post("/api/v1/assessments/start", json={"specialization": "frontend", "grade": "middle", "stack": survey["stack"]})
    assert attempt_response.status_code == 201, attempt_response.text
    attempt = attempt_response.json()
    result = candidate.post(f"/api/v1/assessments/{attempt['id']}/submit", json={"answers": reference_answers(database, attempt["id"])})
    assert result.status_code == 200 and result.json()["result"]["passed"]
    assert result.json()["result"]["confirmed_grade"] == "middle"
    for _ in range(3):
        current = candidate.get("/api/v1/challenges/weekly").json()
        assert current["challenge"]["id"] == changed["challenge"]["id"]
        assert current["challenge"]["specialization"] == "frontend" and current["challenge"]["grade"] == "middle"
    with database() as db:
        assert db.get(Challenge, old["id"]).data == old_data
        assert db.get(Challenge, old["id"]).rubric == old_rubric
        assert db.get(ChallengeSubmission, solved.json()["id"]).result == old_result
        tasks = db.scalars(select(Challenge).where(Challenge.data["assigned_candidate_id"].as_string() == "candidate-1",
            Challenge.data["recurrence_week"].as_string() == before["week_id"])).all()
        assert len(tasks) == 2
        assert db.scalar(select(func.count()).select_from(Notification).where(
            Notification.account_id == "account-1", Notification.kind == "practice.weekly")) == 1


@pytest.mark.parametrize("demo, passed, title", [
    (False, True, "Результат экзамена готов"),
    (False, False, "Результат экзамена готов"),
    (True, True, "Демо-результат экзамена готов"),
])
def test_assessment_notification_names_real_scope_without_repeated_events(database, demo, passed, title):
    candidate = logged()
    assert candidate.post("/api/v1/candidate/survey", json={"industry": "ИТ", "specialization": "backend",
        "grade": "junior", "stack": ["Python", "SQL"]}).status_code == 200
    started = candidate.post("/api/v1/assessments/start", json={"specialization": "backend", "grade": "junior",
        "stack": ["Python", "SQL"], "demo": demo})
    assert started.status_code == 201, started.text
    attempt = started.json()
    before = candidate.get("/api/v1/candidate/profile").json()
    answers = reference_answers(database, attempt["id"]) if passed else {}
    path = f"/api/v1/assessments/{attempt['id']}/submit"
    completed = candidate.post(path, json={"answers": answers})
    assert completed.status_code == 200, completed.text
    result = completed.json()["result"]
    assert result["passed"] is passed and result["scope"] == "global_category"
    assert result["certifies_global_category"] is (passed and not demo)
    assert result["category_changed"] is (passed and not demo)
    profile = candidate.get("/api/v1/candidate/profile").json()
    if passed and not demo:
        assert profile["confirmed_grade"] == "junior" and profile["confirmed_categories"]["backend"]["grade"] == "junior"
    else:
        for field in ["confirmed_grade", "confirmed_categories", "score", "assessment_at"]:
            assert profile[field] == before[field]
    replayed = candidate.post(path, json={"answers": {}})
    assert replayed.status_code == 200 and replayed.json()["result"] == result
    with database() as db:
        notices = db.scalars(select(Notification).where(Notification.account_id == "account-1",
            Notification.kind == "assessment.completed", Notification.data["attempt_id"].as_string() == attempt["id"])).all()
        assert len(notices) == 1 and notices[0].title == title
        assert notices[0].data == {"attempt_id": attempt["id"], "passed": passed, "demo": demo}
        assert db.scalar(select(func.count()).select_from(Outbox).where(Outbox.kind == "notification",
            Outbox.payload["notification_id"].as_string() == notices[0].id)) == 1


def test_real_fsp_demo_link_is_searchable_and_withdrawal_preserves_category(database):
    confirm_fixture(database)
    candidate, employer, outsider = logged(), logged("employer@vector.local"), logged("other@vector.local")
    credentials = {"fsp_id": "FSP-DEMO-001", "proof_code": "VECTOR-2026"}
    assert outsider.post("/api/v1/candidate/fsp/link", json=credentials).status_code == 403
    before = candidate.get("/api/v1/candidate/profile").json()
    linked = candidate.post("/api/v1/candidate/fsp/link", json=credentials)
    assert linked.status_code == 200, linked.text
    assert linked.json()["fsp"]["status"] == "verified_demo"
    filtered = employer.get("/api/v1/employer/candidates?fsp_only=true").json()
    assert filtered["total"] == 1 and filtered["items"][0]["id"] == "candidate-1"
    fsp = filtered["items"][0]["fsp"]
    assert fsp["status"] == "verified_demo" and fsp["source"] == "FSP_DEMO_CONFIRMED" and fsp["demo"] is True
    assert all(item["source"] == "FSP_DEMO_CONFIRMED" and item["is_demo"] for item in fsp["achievements"])
    assert "contacts" not in filtered["items"][0]
    assert candidate.post("/api/v1/candidate/consents", json={"purpose": "fsp", "granted": False}).status_code == 200
    assert employer.get("/api/v1/employer/candidates?fsp_only=true").json()["total"] == 0
    assert employer.get("/api/v1/employer/candidates").json()["total"] == 1
    after = candidate.get("/api/v1/candidate/profile").json()
    for field in ["confirmed_grade", "confirmed_categories", "score", "assessment_at"]:
        assert after[field] == before[field]

"""Opt-in concurrency audit against an isolated, disposable PostgreSQL database.

RUN_PG_AUDIT=1 uses local project runtime credentials without printing them. The
fixture creates a unique vector_backend_audit_* database; never resets vector.
"""
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from uuid import uuid4
import pytest
import psycopg
from psycopg import sql
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker
from app.db import Base, get_db
from app.main import app
from app.models import Account, AssessmentAttempt, Candidate, Challenge, Company, Consent, ContactGrant, Delivery, Invitation, MailMessage, MatchRun, Need, Notification, Outbox
from test_domain_api import PASSWORD_HASH, confirm_fixture, create_attempt, invite, logged, need_body, reference_answers

pytestmark = pytest.mark.skipif(os.getenv("RUN_PG_AUDIT") != "1", reason="Set RUN_PG_AUDIT=1 for the isolated local PostgreSQL audit")


@pytest.fixture(scope="module")
def audit_engine():
    workspace = Path(__file__).resolve().parents[3]
    config = json.loads((workspace / ".local/runtime.json").read_text())
    db_name = "vector_backend_audit_" + uuid4().hex[:12]
    assert db_name.startswith("vector_backend_audit_")
    try:
        admin = psycopg.connect(host="127.0.0.1",port=config["pg_port"],user="vector_admin",
                               password=config["pg_admin_password"],dbname="postgres",autocommit=True,connect_timeout=5)
    except psycopg.Error:
        raise RuntimeError("Isolated PostgreSQL audit connection unavailable; check local runtime credentials.") from None
    admin.execute(sql.SQL("CREATE DATABASE {} OWNER vector").format(sql.Identifier(db_name)))
    url = URL.create("postgresql+psycopg",username="vector",password=config["pg_app_password"],
                     host="127.0.0.1",port=config["pg_port"],database=db_name)
    engine = create_engine(url,pool_size=12,max_overflow=4,pool_pre_ping=True)
    try:
        yield engine
    finally:
        engine.dispose()
        # Drop only the exact, unique database created by this audit fixture.
        admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(db_name)))
        admin.close()


@pytest.fixture()
def postgres(audit_engine,monkeypatch):
    Base.metadata.drop_all(audit_engine)
    Base.metadata.create_all(audit_engine)
    sessions = sessionmaker(bind=audit_engine,expire_on_commit=False)
    with sessions() as db:
        for index,email,role in [(1,"candidate@vector.local","candidate"),(3,"employer@vector.local","employer")]:
            account = Account(id=f"account-{index}",name=f"Synthetic {index}",email=email,password_hash=PASSWORD_HASH,
                              role=role,email_verified=True)
            db.add(account)
            db.flush()
            db.add(Consent(account_id=account.id,purpose="processing",granted=True))
            if role == "candidate":
                db.add(Candidate(id="candidate-1",account_id=account.id,alias="Anonymous",specialization="backend",
                    declared_grade="junior",skills=["SQL"],preferences={"salary_from":100000,"salary_to":200000,
                    "work_format":"remote","employment":"full_time"}))
            else:
                db.add(Company(id="company-3",account_id=account.id,name="Test Company",
                               description="Вымышленная компания аудита",contact=email))
        db.commit()
    def override():
        with sessions() as db:
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise
    app.dependency_overrides[get_db] = override
    import app.worker as worker
    monkeypatch.setattr(worker,"SessionLocal",sessions)
    yield sessions
    app.dependency_overrides.clear()


def parallel(*operations):
    gate = threading.Barrier(len(operations))
    def run(operation):
        gate.wait(timeout=10)
        return operation()
    with ThreadPoolExecutor(max_workers=len(operations)) as pool:
        return list(pool.map(run,operations))


def test_postgres_simultaneous_start_creates_one_active_attempt(postgres):
    candidate = logged()
    assert candidate.post("/api/v1/candidate/survey",json={"industry":"ИТ","specialization":"backend",
        "grade":"junior","stack":["Python","SQL"]}).status_code == 200
    clients = [logged() for _ in range(6)]
    responses = parallel(*[lambda client=client:client.post("/api/v1/assessments/start",json={
        "specialization":"backend","grade":"junior","stack":["Python","SQL"]}) for client in clients])
    assert all(response.status_code == 201 for response in responses)
    assert len({response.json()["id"] for response in responses}) == 1
    with postgres() as db:
        assert db.scalar(select(func.count()).select_from(AssessmentAttempt)) == 1


def test_postgres_duplicate_submit_produces_one_result_and_event(postgres):
    candidate = logged()
    attempt = create_attempt(candidate)
    answers = reference_answers(postgres,attempt["id"])
    clients = [logged() for _ in range(4)]
    responses = parallel(*[lambda client=client:client.post(f"/api/v1/assessments/{attempt['id']}/submit",json={"answers":answers})
                            for client in clients])
    assert all(response.status_code == 200 and response.json()["result"]["score"] == 100 for response in responses)
    with postgres() as db:
        assert db.scalar(select(func.count()).select_from(Notification).where(Notification.kind == "assessment.completed")) == 1
        assert db.get(Candidate,"candidate-1").confirmed_grade == "junior"


def test_postgres_accept_vs_withdraw_is_atomic_and_grant_matches_winner(postgres):
    confirm_fixture(postgres)
    employer,candidate = logged("employer@vector.local"),logged()
    invitation = invite(employer).json()
    accepted,withdrawn = parallel(lambda:candidate.post(f"/api/v1/invitations/{invitation['id']}/accept"),
                                  lambda:employer.post(f"/api/v1/invitations/{invitation['id']}/withdraw"))
    assert sorted([accepted.status_code,withdrawn.status_code]) == [200,409]
    with postgres() as db:
        status = db.get(Invitation,invitation["id"]).status
        grants = db.scalar(select(func.count()).select_from(ContactGrant))
        assert (status,grants) in {("accepted",1),("withdrawn",0)}


def test_postgres_repeated_accept_has_one_company_scoped_grant(postgres):
    confirm_fixture(postgres)
    employer = logged("employer@vector.local")
    invitation = invite(employer).json()
    clients = [logged() for _ in range(6)]
    responses = parallel(*[lambda client=client:client.post(f"/api/v1/invitations/{invitation['id']}/accept") for client in clients])
    assert all(response.status_code == 200 for response in responses)
    with postgres() as db:
        assert db.scalar(select(func.count()).select_from(ContactGrant)) == 1
        assert db.scalar(select(func.count()).select_from(Outbox).where(Outbox.kind == "ats.invitation_accepted")) == 1


def test_postgres_two_workers_skip_locked_and_deliver_once(postgres):
    from app.worker import consume_once
    confirm_fixture(postgres)
    employer,candidate = logged("employer@vector.local"),logged()
    invitation = invite(employer).json()
    candidate.post(f"/api/v1/invitations/{invitation['id']}/accept")
    with postgres() as db:
        for index in range(20):
            db.add(Outbox(kind="notification",payload={"audit_fixture":index}))
        db.commit()
    responses = parallel(lambda:consume_once(12),lambda:consume_once(12))
    assert sum(responses) == 23
    with postgres() as db:
        assert db.scalar(select(func.count()).select_from(Outbox).where(Outbox.status == "completed")) == 23
        assert db.scalar(select(func.count()).select_from(Delivery)) == 1
        assert set(db.scalars(select(Outbox.attempts)).all()) == {1}


def test_postgres_processing_revocation_wins_over_concurrent_publication(postgres):
    confirm_fixture(postgres)
    publisher,revoker = logged(),logged()
    results = parallel(lambda:publisher.post("/api/v1/candidate/publication",json={"published":True,"consent_publication":True}),
        lambda:revoker.post("/api/v1/auth/consents",json={"consent_processing":False}))
    assert results[1].status_code == 200 and results[0].status_code in {200,403}
    with postgres() as db:
        assert not db.get(Candidate,"candidate-1").published
    assert logged("employer@vector.local").get("/api/v1/employer/candidates").json()["items"] == []


def test_postgres_processing_revocation_cannot_leave_a_new_application_grant(postgres):
    confirm_fixture(postgres)
    employer,applicant,revoker = logged("employer@vector.local"),logged(),logged()
    vacancy = employer.post("/api/v1/vacancies",json=need_body()).json()
    results = parallel(lambda:applicant.post(f"/api/v1/vacancies/{vacancy['id']}/apply",json={"consent_contacts":True}),
        lambda:revoker.post("/api/v1/auth/consents",json={"consent_processing":False}))
    assert results[1].status_code == 200 and results[0].status_code in {201,403}
    with postgres() as db:
        assert not db.get(Candidate,"candidate-1").published
        assert db.scalar(select(func.count()).select_from(ContactGrant).where(ContactGrant.revoked_at.is_(None))) == 0


def test_postgres_weekly_get_and_two_schedulers_create_one_task_and_notification(postgres):
    from app.practice import schedule_weekly_practice
    clients = [logged() for _ in range(6)]
    def schedule():
        with postgres() as db:
            count = schedule_weekly_practice(db)
            db.commit()
            return count
    responses = parallel(*[lambda client=client: client.get("/api/v1/challenges/weekly") for client in clients],
                         schedule, schedule)
    assert all(response.status_code == 200 for response in responses[:6])
    assert len({response.json()["challenge"]["id"] for response in responses[:6]}) == 1
    with postgres() as db:
        assert db.scalar(select(func.count()).select_from(Challenge)) == 1
        assert db.scalar(select(func.count()).select_from(Notification).where(Notification.kind == "practice.weekly")) == 1


def test_postgres_processing_revocation_is_serialized_with_answer_save(postgres):
    candidate, saver, revoker = logged(), logged(), logged()
    attempt = create_attempt(candidate)
    answers = reference_answers(postgres, attempt["id"])
    response, revoked = parallel(lambda: saver.put(f"/api/v1/assessments/{attempt['id']}/answers", json={"answers": answers}),
        lambda: revoker.post("/api/v1/auth/consents", json={"consent_processing": False}))
    assert revoked.status_code == 200 and response.status_code in {200, 403}
    assert saver.put(f"/api/v1/assessments/{attempt['id']}/answers", json={"answers": answers}).status_code == 403
    with postgres() as db:
        assert db.get(AssessmentAttempt, attempt["id"]).result is None
        assert db.get(Candidate, "candidate-1").confirmed_grade is None


def test_postgres_pending_dispatch_waits_for_owner_withdrawal_and_rechecks_after_commit(postgres, monkeypatch):
    import app.worker as worker
    confirm_fixture(postgres)
    employer, candidate = logged('employer@vector.local'), logged()
    invitation = invite(employer).json()
    assert candidate.post(f"/api/v1/invitations/{invitation['id']}/accept").status_code == 200
    with postgres() as db:
        for row in db.scalars(select(Outbox).where(Outbox.kind == 'notification')):
            row.status = 'completed'
        db.commit()
    entered_owner_check = threading.Event()
    real_check = worker.company_processing_active
    def observed_check(db, company, lock=False):
        assert lock
        entered_owner_check.set()
        return real_check(db, company, lock=lock)
    monkeypatch.setattr(worker, 'company_processing_active', observed_check)
    monkeypatch.setattr(worker, 'settings', replace(worker.settings,
        ats_webhook_url='http://127.0.0.1:8090/events', ats_webhook_secret='synthetic-test-key'))
    attempted_transport = []
    def forbidden_transport(*args, **kwargs):
        attempted_transport.append(True)
        raise AssertionError('Committed withdrawal must win before transport')
    monkeypatch.setattr(worker.httpx, 'post', forbidden_transport)
    # This transaction follows the actual consent route's owner-row lock and
    # insert. The worker reaches that same lock while withdrawal is uncommitted.
    with ThreadPoolExecutor(max_workers=1) as pool:
        with postgres() as revocation:
            revocation.scalar(select(Account).where(Account.id == 'account-3').with_for_update())
            revocation.add(Consent(account_id='account-3', purpose='processing', granted=False))
            revocation.flush()
            dispatch = pool.submit(worker.consume_once, 1)
            assert entered_owner_check.wait(10)
            with pytest.raises(TimeoutError):
                dispatch.result(timeout=.1)
            revocation.commit()
        assert dispatch.result(timeout=10) == 0
    assert attempted_transport == []
    with postgres() as db:
        event = db.scalar(select(Outbox).where(Outbox.kind == 'ats.invitation_accepted'))
        assert event.status == 'cancelled_company_unavailable' and event.completed_at and event.attempts == 1
        assert db.scalar(select(func.count()).select_from(Delivery)) == 0


def test_postgres_invitation_rechecks_owner_after_dependency_passed_but_withdrawal_committed(postgres, monkeypatch):
    import app.hiring as hiring
    confirm_fixture(postgres)
    employer, revoker = logged('employer@vector.local'), logged('employer@vector.local')
    entered_creation = threading.Event()
    real_company_for = hiring.company_for
    def observed_company_for(db, account):
        # EmployerUser has already checked consent before route execution.
        company = real_company_for(db, account)
        entered_creation.set()
        return company
    monkeypatch.setattr(hiring, 'company_for', observed_company_for)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with postgres() as candidate_gate:
            candidate_gate.scalar(select(Candidate).where(Candidate.id == 'candidate-1').with_for_update())
            creation = pool.submit(lambda:invite(employer))
            assert entered_creation.wait(10)
            assert revoker.post('/api/v1/auth/consents', json={'consent_processing':False}).status_code == 200
            with pytest.raises(TimeoutError):
                creation.result(timeout=.1)
            candidate_gate.commit()
        response = creation.result(timeout=10)
    assert response.status_code == 409 and response.json()['code'] == 'COMPANY_UNAVAILABLE'
    with postgres() as db:
        assert db.scalar(select(func.count()).select_from(Invitation)) == 0
        assert db.scalar(select(func.count()).select_from(Notification).where(Notification.kind == 'invitation.received')) == 0


def test_postgres_first_delivery_commits_and_owner_lock_releases_before_unrelated_second_transport(postgres, monkeypatch):
    import httpx
    import app.worker as worker
    confirm_fixture(postgres)
    employer, candidate = logged('employer@vector.local'), logged()
    invitation = invite(employer).json()
    assert candidate.post(f"/api/v1/invitations/{invitation['id']}/accept").status_code == 200
    with postgres() as db:
        for row in db.scalars(select(Outbox).where(Outbox.kind == 'notification')):
            row.status = 'completed'
        mail = MailMessage(to='independent@example.invalid', subject='Synthetic separate mail', body='No participant information')
        db.add(mail)
        db.flush()
        db.add(Outbox(kind='email.verification', payload={'mail_id':mail.id}))
        db.commit()
    monkeypatch.setattr(worker, 'settings', replace(worker.settings, smtp_host='127.0.0.1', smtp_port=1025,
        ats_webhook_url='http://127.0.0.1:8090/events', ats_webhook_secret='synthetic-test-key'))
    transports = []
    def successful_ats(url, content, headers, **kwargs):
        transports.append(json.loads(content))
        return httpx.Response(202, request=httpx.Request('POST', url))
    monkeypatch.setattr(worker.httpx, 'post', successful_ats)
    mail_entered, release_mail = threading.Event(), threading.Event()
    class SlowIndependentSMTP:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def send_message(self, message):
            mail_entered.set()
            assert release_mail.wait(10)
    monkeypatch.setattr(worker.smtplib, 'SMTP', SlowIndependentSMTP)
    with ThreadPoolExecutor(max_workers=2) as pool:
        dispatch = pool.submit(worker.consume_once, 2)
        try:
            assert mail_entered.wait(10)
            with postgres() as db:
                # With one transaction for the entire batch, this is still zero
                # and the owner consent route is blocked by the first event.
                assert db.scalar(select(func.count()).select_from(Delivery)) == 1
            withdrawal = pool.submit(lambda:employer.post('/api/v1/auth/consents', json={'consent_processing':False}))
            assert withdrawal.result(timeout=5).status_code == 200
            assert not release_mail.is_set()
        finally:
            release_mail.set()
        assert dispatch.result(timeout=10) == 2
    assert len(transports) == 1 and 'contacts' not in transports[0]
    with postgres() as db:
        assert db.scalar(select(func.count()).select_from(Delivery)) == 1
        assert db.scalar(select(Consent.granted).where(Consent.account_id == 'account-3', Consent.purpose == 'processing')
                         .order_by(Consent.created_at.desc()).limit(1)) is False
        assert set(db.scalars(select(Outbox.status)).all()) == {'completed'}


@pytest.mark.parametrize("semantic_enabled", [False, True], ids=["semantic-neutral", "cpu-tfidf"])
def test_postgres_matching_persists_exact_engine_version_and_public_run(postgres, semantic_enabled):
    """SQLite accepts overlong VARCHAR values; PostgreSQL must enforce the real limit.

    TF-IDF is an explicit persisted test-fixture opt-in, not a public need field or
    a change to the neutral production default.
    """
    from app.engines.matching import ALGORITHM_VERSION
    confirm_fixture(postgres)
    employer, candidate = logged("employer@vector.local"), logged()
    created_need = employer.post("/api/v1/employer/needs", json=need_body(skills=["SQL"]))
    assert created_need.status_code == 201, created_need.text
    need_id = created_need.json()["id"]
    with postgres() as db:
        assert db.scalar(text("SELECT character_maximum_length FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='match_runs' AND column_name='algorithm_version'")) == 80
        need = db.get(Need, need_id)
        assert need.company_id == "company-3"
        if semantic_enabled:
            need.data = {**need.data, "semantic_enabled": True}
            db.commit()
    assert candidate.post("/api/v1/employer/matches", json={"need_id": need_id}).status_code == 403
    response = employer.post("/api/v1/employer/matches", json={"need_id": need_id})
    assert response.status_code == 201, response.text
    public = response.json()
    expected = ALGORITHM_VERSION.replace("semantic-neutral", "cpu-tfidf") if semantic_enabled else ALGORITHM_VERSION
    assert len(expected) <= 80 and public["algorithm_version"] == expected
    assert public["total"] == 1 and public["items"][0]["candidate"]["id"] == "candidate-1"
    assert "contacts" not in public["items"][0]["candidate"]
    assert public["items"][0]["semantic_status"] == (
        "calculated_lexical_similarity" if semantic_enabled else "disabled_neutral_constant")
    persisted = employer.get(f"/api/v1/employer/matches/{public['id']}")
    assert persisted.status_code == 200
    saved = persisted.json()
    # PostgreSQL may return the session timezone; compare the same actual instant.
    assert datetime.fromisoformat(saved["created_at"]) == datetime.fromisoformat(public["created_at"])
    assert {key: value for key, value in saved.items() if key != "created_at"} == {
        key: value for key, value in public.items() if key != "created_at"}
    with postgres() as db:
        row = db.get(MatchRun, public["id"])
        assert row.company_id == "company-3" and row.need_id == need_id
        assert row.algorithm_version == expected == row.results[0]["algorithm_version"]
        assert row.results[0]["candidate_id"] == "candidate-1"
        if semantic_enabled:
            assert row.need_snapshot["semantic_enabled"] is True
            assert row.results[0]["semantic"]["model_version"] == "vector-cpu-word-char-tfidf-v1"
            assert len(row.results[0]["semantic"]["artifact_sha256"]) == 64
        else:
            assert not row.need_snapshot.get("semantic_enabled", False)
            assert row.results[0]["semantic"]["value"] == .5

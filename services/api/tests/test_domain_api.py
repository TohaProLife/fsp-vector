"""Integration tests use real routes, transactions and engine grading.

Fixtures are synthetic; no tests alter a production participant's results.
"""
import json
import hashlib
import hmac
from dataclasses import replace
from datetime import timedelta
from urllib.parse import parse_qs, urlparse
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.auth import digest, hash_password
from app.db import Base, get_db
from app.main import app
from app.models import Account, AssessmentAttempt, Candidate, Company, Consent, ContactGrant, Delivery, FspRecord, Invitation, MailMessage, Need, Outbox, Vacancy, utcnow

PASSWORD = "VectorDemo2026!"
PASSWORD_HASH = hash_password(PASSWORD)


@pytest.fixture()
def database(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as db:
        for index, email, role in [(1,"candidate@vector.local","candidate"), (2,"other@vector.local","candidate"),
                                   (3,"employer@vector.local","employer"), (4,"employer2@vector.local","employer")]:
            account = Account(id=f"account-{index}", name=f"Private Person {index}", email=email,
                              password_hash=PASSWORD_HASH, role=role, email_verified=True)
            db.add(account)
            db.flush()
            db.add(Consent(account_id=account.id, purpose="processing", granted=True))
            if role == "candidate":
                db.add(Candidate(id=f"candidate-{index}", account_id=account.id, alias=f"Anonymous {index}",
                                 title="Backend", specialization="backend", declared_grade="junior",
                                 skills=["SQL", "API"], preferences={"work_format":"remote","employment":"full_time",
                                 "salary_from":100000,"salary_to":200000}, contacts={"phone":"PRIVATE-PHONE"}))
            else:
                db.add(Company(id=f"company-{index}", account_id=account.id, name=f"Company {index}",
                               description="Подробное описание вымышленной компании", contact=email))
        db.add(FspRecord(fsp_id="FSP-DEMO-001", email="candidate@vector.local", proof_hash=digest("VECTOR-2026"),
                         achievements=[{"title":"Synthetic championship","source":"FSP_DEMO_CONFIRMED","is_demo":True}]))
        db.commit()

    def override_db():
        with sessions() as db:
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise

    app.dependency_overrides[get_db] = override_db
    import app.platform as platform
    import app.worker as worker
    monkeypatch.setattr(platform, "SessionLocal", sessions)
    monkeypatch.setattr(worker, "SessionLocal", sessions)
    yield sessions
    app.dependency_overrides.clear()
    engine.dispose()


def logged(email="candidate@vector.local"):
    client = TestClient(app)
    response = client.post("/api/v1/auth/login", json={"email":email,"password":PASSWORD})
    assert response.status_code == 200, response.text
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return client


def confirm_fixture(sessions, candidate_id="candidate-1"):
    with sessions() as db:
        candidate = db.get(Candidate, candidate_id)
        candidate.confirmed_grade, candidate.score, candidate.published = "junior", 88, True
        candidate.confirmed_categories = {"backend":{"grade":"junior","score":88,"confirmed_at":utcnow().isoformat(),"source":"SYNTHETIC_TEST_FIXTURE"}}
        candidate.assessment_at = utcnow()
        candidate.evidence = [{"skill":"SQL","source":"ASSESSMENT_VERIFIED","status":"verified","strength":.88,
                               "scope":{"specialization":"backend"}}]
        db.add(Consent(account_id=candidate.account_id, purpose="publication", granted=True))
        db.commit()


def need_body(**updates):
    return {"title":"Backend для API","description":"Нужен разработчик API и SQL","specialization":"backend",
            "grade":"junior","skills":["Python"],"required_skills":["SQL"],"salary_from":120000,"salary_to":180000,
            "work_format":"remote","employment":"full_time","team":"Команда API",**updates}


def invite(client, candidate_id="candidate-1", **updates):
    return client.post("/api/v1/invitations", json={"candidate_id":candidate_id,"title":"Предложение Backend",
        "message":"Приглашаем обсудить работу в платформенной команде.","salary_from":120000,"salary_to":180000,
        "work_format":"remote","employment":"full_time","contact":"hr@company.invalid",**updates})


def create_attempt(client):
    response = client.post("/api/v1/candidate/survey", json={"industry":"ИТ","specialization":"backend",
        "grade":"junior","stack":["Python","SQL"],"work_format":"remote"})
    assert response.status_code == 200, response.text
    response = client.post("/api/v1/assessments/start", json={"specialization":"backend","grade":"junior","stack":["Python","SQL"]})
    assert response.status_code == 201, response.text
    return response.json()


def reference_answers(sessions, attempt_id):
    from evaluation.reference_solvers import reference_answer
    with sessions() as db:
        public_items = db.get(AssessmentAttempt, attempt_id).private_form["items"]
        return {item["id"]:reference_answer(item) for item in public_items}


def test_email_verification_is_required_and_replay_rejected(database):
    client = TestClient(app)
    response = client.post("/api/v1/auth/register", json={"name":"Новый кандидат","email":"new@example.invalid",
        "password":PASSWORD,"role":"candidate","consent_processing":True})
    assert response.status_code == 201
    response = client.post("/api/v1/auth/login", json={"email":"new@example.invalid","password":PASSWORD})
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    assert client.get("/api/v1/candidate/profile").json()["code"] == "EMAIL_NOT_VERIFIED"
    letter = client.get("/api/v1/auth/demo-mailbox?email=new@example.invalid").json()["items"][0]
    token = parse_qs(urlparse(letter["verification_url"]).query)["token"][0]
    assert client.get(f"/api/v1/auth/verify?token={token}").status_code == 200
    assert client.get(f"/api/v1/auth/verify?token={token}").status_code == 400
    assert client.get("/api/v1/candidate/profile").status_code == 200


def test_session_is_opaque_httponly_and_csrf_enforced(database):
    client = logged()
    assert "vector_session" in client.cookies
    assert client.get("/api/v1/auth/me").headers["cache-control"] == "no-store"
    client.headers.pop("X-CSRF-Token")
    result = client.patch("/api/v1/candidate/profile", json={"title":"Изменение"})
    assert result.status_code == 403 and result.json()["code"] == "CSRF_REJECTED"
    client.headers["X-CSRF-Token"] = client.get("/api/v1/auth/me").json()["csrf_token"]
    assert client.patch("/api/v1/candidate/profile", json={"title":"Изменение"},headers={"Origin":"https://attacker.invalid"}).status_code == 403
    assert client.post("/api/v1/auth/logout").status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401


def test_role_and_grade_mass_assignment_are_rejected(database):
    candidate, employer = logged(), logged("employer@vector.local")
    assert candidate.get("/api/v1/employer/company").status_code == 403
    assert employer.get("/api/v1/candidate/profile").status_code == 403
    assert candidate.patch("/api/v1/candidate/profile",json={"confirmed_grade":"senior","score":100,"published":True}).status_code == 422
    assert candidate.get("/api/v1/candidate/profile").json()["confirmed_grade"] is None
    assert candidate.post("/api/v1/candidate/publication",json={"published":True,"consent_publication":True}).status_code == 409


def test_actual_exam_persists_answers_hides_oracle_and_assigns_category(database):
    client = logged()
    attempt = create_attempt(client)
    exposed = json.dumps(attempt)
    assert len(attempt["items"]) == 12
    for forbidden in ["_oracle","private_payload","_private","expected","generated_at"]:
        assert forbidden not in exposed
    assert client.get(f"/api/v1/assessments/{attempt['id']}").json()["id"] == attempt["id"]
    answers = reference_answers(database, attempt["id"])
    saved = client.put(f"/api/v1/assessments/{attempt['id']}/answers",json={"answers":answers})
    assert saved.status_code == 200
    completed = client.post(f"/api/v1/assessments/{attempt['id']}/submit",json={"answers":{}}).json()
    assert completed["result"]["score"] == 100 and completed["result"]["passed"]
    assert completed["result"]["category_changed"]
    profile = client.get("/api/v1/candidate/profile").json()
    assert profile["confirmed_grade"] == "junior" and profile["evidence"]
    repeat = client.post(f"/api/v1/assessments/{attempt['id']}/submit",json={"answers":{}})
    assert repeat.json()["result"]["score"] == 100
    assert client.post("/api/v1/assessments/start",json={"specialization":"backend","grade":"junior","stack":["Python"]}).status_code == 409


def test_exam_ownership_unknown_answers_and_time_limit(database):
    client = logged()
    attempt = create_attempt(client)
    assert logged("other@vector.local").get(f"/api/v1/assessments/{attempt['id']}").status_code == 404
    assert client.put(f"/api/v1/assessments/{attempt['id']}/answers",json={"answers":{"alien":"correct"}}).status_code == 400
    with database() as db:
        db.get(AssessmentAttempt,attempt["id"]).expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    assert client.post(f"/api/v1/assessments/{attempt['id']}/submit",json={"answers":{}}).status_code == 409
    assert client.get(f"/api/v1/assessments/{attempt['id']}").json()["status"] == "expired"
    assert client.get("/api/v1/candidate/profile").json()["confirmed_grade"] is None


def test_failure_and_demo_attempt_never_downgrade_or_assign_grade(database):
    confirm_fixture(database)
    client = logged()
    attempt = create_attempt(client)
    result = client.post(f"/api/v1/assessments/{attempt['id']}/submit",json={"answers":{}}).json()["result"]
    assert not result["passed"] and not result["category_changed"] and result["confirmed_grade"] == "junior"
    other = logged("other@vector.local")
    assert other.post("/api/v1/candidate/survey",json={"industry":"ИТ","specialization":"backend","grade":"junior","stack":["Python"]}).status_code == 200
    attempt = other.post("/api/v1/assessments/start",json={"specialization":"backend","grade":"junior","stack":["Python"],"demo":True}).json()
    result = other.post(f"/api/v1/assessments/{attempt['id']}/submit",json={"answers":reference_answers(database,attempt["id"])}).json()["result"]
    assert result["passed"] and not result["category_changed"] and result["confirmed_grade"] is None
    assert not result["category_change_allowed"] and not result["certifies_global_category"]


def test_contact_acceptance_is_company_scoped_idempotent_and_revocable(database):
    confirm_fixture(database)
    candidate, employer, outsider = logged(), logged("employer@vector.local"), logged("employer2@vector.local")
    safe = employer.get("/api/v1/employer/candidates/candidate-1").json()
    assert "contacts" not in safe and "Private Person" not in json.dumps(safe)
    response = invite(employer)
    assert response.status_code == 201, response.text
    invitation_id = response.json()["id"]
    assert outsider.get(f"/api/v1/invitations/{invitation_id}").status_code == 404
    assert employer.post(f"/api/v1/invitations/{invitation_id}/accept").status_code == 403
    accepted = candidate.post(f"/api/v1/invitations/{invitation_id}/accept").json()
    assert accepted["contacts_open"]
    assert employer.get("/api/v1/employer/candidates/candidate-1").json()["contacts"]["phone"] == "PRIVATE-PHONE"
    assert "contacts" not in outsider.get("/api/v1/employer/candidates/candidate-1").json()
    grant_id = accepted["contact_grant_id"]
    assert candidate.post(f"/api/v1/candidate/contact-grants/{grant_id}/revoke").status_code == 200
    assert "contacts" not in employer.get("/api/v1/employer/candidates/candidate-1").json()
    assert not candidate.post(f"/api/v1/invitations/{invitation_id}/accept").json()["contacts_open"]
    with database() as db:
        assert len(db.scalars(select(ContactGrant)).all()) == 1
        assert len(db.scalars(select(Outbox).where(Outbox.kind == "ats.invitation_accepted")).all()) == 1


def test_saved_matches_recheck_publication_and_processing_consent(database):
    confirm_fixture(database)
    candidate, employer, outsider = logged(), logged("employer@vector.local"), logged("employer2@vector.local")
    need = employer.post("/api/v1/employer/needs",json=need_body()).json()
    response = employer.post("/api/v1/employer/matches",json={"need_id":need["id"]})
    assert response.status_code == 201, response.text
    run = response.json()
    assert run["total"] == 1 and "contacts" not in run["items"][0]["candidate"]
    assert run["items"][0]["semantic_status"] == "disabled_neutral_constant"
    saved = employer.get(f"/api/v1/employer/matches/{run['id']}").json()
    assert saved["items"][0]["semantic_status"] == "disabled_neutral_constant"
    assert outsider.get(f"/api/v1/employer/matches/{run['id']}").status_code == 404
    assert outsider.get(f"/api/v1/employer/needs/{need['id']}").status_code == 404
    assert candidate.post("/api/v1/candidate/publication",json={"published":False}).status_code == 200
    assert employer.get(f"/api/v1/employer/matches/{run['id']}").json()["items"] == []
    assert candidate.post("/api/v1/candidate/publication",json={"published":True,"consent_publication":True}).status_code == 200
    assert candidate.post("/api/v1/candidate/consents",json={"purpose":"processing","granted":False}).status_code == 200
    assert employer.get("/api/v1/employer/candidates").json()["items"] == []
    assert employer.get(f"/api/v1/employer/matches/{run['id']}").json()["items"] == []
    assert candidate.post("/api/v1/candidate/consents",json={"purpose":"publication","granted":True}).status_code == 409
    assert candidate.post("/api/v1/candidate/consents",json={"purpose":"fsp","granted":True}).status_code == 409


def test_fsp_ownership_is_bound_to_verified_identity(database):
    client = logged()
    assert client.post("/api/v1/candidate/fsp/link",json={"fsp_id":"FSP-DEMO-001","proof_code":"wrong"}).status_code == 403
    assert logged("other@vector.local").post("/api/v1/candidate/fsp/link",json={"fsp_id":"FSP-DEMO-001","proof_code":"VECTOR-2026"}).status_code == 403
    response = client.post("/api/v1/candidate/fsp/link",json={"fsp_id":"FSP-DEMO-001","proof_code":"VECTOR-2026"})
    assert response.status_code == 200 and response.json()["fsp"]["source"] == "FSP_DEMO_CONFIRMED"
    assert client.delete("/api/v1/candidate/fsp/link").json()["fsp"]["achievements"] == []


def test_salary_invariants_are_enforced_by_api_and_database(database):
    confirm_fixture(database)
    employer = logged("employer@vector.local")
    assert invite(employer,salary_from=200000,salary_to=100000).status_code == 400
    assert invite(employer,salary_from=0).status_code == 422
    assert employer.post("/api/v1/vacancies",json=need_body(salary_from=200000,salary_to=100000)).status_code == 400
    with database() as db:
        db.add(Invitation(company_id="company-3",candidate_id="candidate-1",data={},company_snapshot={},salary_from=0,salary_to=100))
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()


def test_self_application_opens_only_target_company_and_duplicate_does_not_restore_grant(database):
    employer, candidate, outsider = logged("employer@vector.local"), logged(), logged("employer2@vector.local")
    vacancy = employer.post("/api/v1/vacancies",json=need_body()).json()
    response = candidate.post(f"/api/v1/vacancies/{vacancy['id']}/apply",json={"message":"Хочу обсудить роль","consent_contacts":True})
    assert response.status_code == 201
    apps = employer.get("/api/v1/applications").json()["items"]
    assert apps[0]["candidate"]["contacts"]["phone"] == "PRIVATE-PHONE"
    assert outsider.get("/api/v1/applications").json()["items"] == []
    assert outsider.patch(f"/api/v1/applications/{apps[0]['id']}",json={"status":"offer"}).status_code == 404
    grant = candidate.get("/api/v1/candidate/profile").json()["contact_grants"][0]
    assert candidate.post(f"/api/v1/candidate/contact-grants/{grant['id']}/revoke").status_code == 200
    candidate.post(f"/api/v1/vacancies/{vacancy['id']}/apply",json={"consent_contacts":True})
    assert "contacts" not in employer.get("/api/v1/applications").json()["items"][0]["candidate"]


def test_block_and_withdraw_prevent_new_contacts(database):
    confirm_fixture(database)
    employer, candidate = logged("employer@vector.local"), logged()
    invitation = invite(employer).json()
    assert employer.post(f"/api/v1/invitations/{invitation['id']}/withdraw").status_code == 200
    assert candidate.post(f"/api/v1/invitations/{invitation['id']}/accept").status_code == 409
    assert candidate.post("/api/v1/candidate/companies/company-3/block").status_code == 200
    assert invite(employer).status_code == 403


def test_outbox_delivery_is_idempotent_and_revocation_cancels_pending_ats(database):
    from app.worker import consume_once
    confirm_fixture(database)
    employer, candidate = logged("employer@vector.local"), logged()
    invitation = invite(employer).json()
    accepted = candidate.post(f"/api/v1/invitations/{invitation['id']}/accept").json()
    assert consume_once() >= 1
    assert consume_once() == 0
    delivery = employer.get("/api/v1/employer/ats-deliveries").json()["items"][0]
    assert "contacts" not in json.dumps(delivery)
    with database() as db:
        assert len(db.scalars(select(Delivery)).all()) == 1
    # A separate accepted event is cancelled if permission is withdrawn before delivery.
    candidate.post(f"/api/v1/candidate/contact-grants/{accepted['contact_grant_id']}/revoke")
    with database() as db:
        db.add(Outbox(kind="ats.invitation_accepted",payload={"company_id":"company-3","candidate_id":"candidate-1",
            "grant_id":accepted["contact_grant_id"],"invitation_id":invitation["id"]}))
        db.commit()
    consume_once()
    with database() as db:
        assert len(db.scalars(select(Delivery)).all()) == 1
        assert db.scalar(select(Outbox).where(Outbox.status == "cancelled_permission_revoked"))


def test_notification_read_is_owner_scoped_and_quality_claims_are_honest(database):
    confirm_fixture(database)
    employer, candidate, outsider = logged("employer@vector.local"), logged(), logged("other@vector.local")
    invite(employer)
    notification = candidate.get("/api/v1/notifications").json()["items"][0]
    assert outsider.post("/api/v1/notifications/read",json={"ids":[notification["id"]]}).json()["read"] == 0
    assert candidate.post("/api/v1/notifications/read",json={"ids":[notification["id"]]}).json()["read"] == 1
    quality = candidate.get("/api/v1/quality/summary").json()
    assert quality["human_pilot"]["sample_size"] == 0 and quality["runtime"]["judge"] == "unavailable_fail_closed"


def test_pdf_is_real_unicode_and_resume_import_cannot_publish_or_verify(database):
    import io
    from pypdf import PdfReader
    client = logged()
    pdf = client.get("/api/v1/candidate/profile.pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF-")
    assert "ФСП" in PdfReader(io.BytesIO(pdf.content)).pages[0].extract_text()
    assert client.post("/api/v1/candidate/resume-import",files={"file":("bad.pdf",b"not pdf","application/pdf")}).status_code == 415
    result = client.post("/api/v1/candidate/resume-import",files={"file":("resume.pdf",pdf.content,"application/pdf")}).json()
    assert result["source"] == "SELF_DECLARED" and not result["persisted"]
    assert client.get("/api/v1/candidate/profile").json()["confirmed_grade"] is None


def test_chunked_body_limit_and_auth_throttle_are_real(database):
    client = logged()
    response = client.patch("/api/v1/candidate/profile", content=(b"x" * 1_000_000 for _ in range(5)),
                            headers={"Content-Type":"application/json"})
    assert response.status_code == 413 and response.json()["code"] == "BODY_TOO_LARGE"
    anonymous = TestClient(app)
    for _ in range(10):
        assert anonymous.post("/api/v1/auth/login",json={"email":"missing@example.invalid","password":"wrong"}).status_code == 401
    assert anonymous.post("/api/v1/auth/login",json={"email":"missing@example.invalid","password":"wrong"}).status_code == 429


def test_employer_processing_consent_can_be_regranted_without_bypass(database):
    employer = logged("employer@vector.local")
    assert employer.post("/api/v1/auth/consents",json={"consent_processing":False}).status_code == 200
    assert employer.get("/api/v1/employer/company").status_code == 403
    assert not employer.get("/api/v1/auth/me").json()["consent_processing"]
    assert employer.post("/api/v1/auth/consents",json={"consent_processing":True}).status_code == 200
    assert employer.get("/api/v1/employer/company").status_code == 200


def test_same_grade_success_refreshes_evidence_without_claiming_category_change(database):
    confirm_fixture(database)
    candidate = logged()
    attempt = create_attempt(candidate)
    completed = candidate.post(f"/api/v1/assessments/{attempt['id']}/submit",json={"answers":reference_answers(database,attempt["id"])}).json()
    assert completed["result"]["passed"] and not completed["result"]["category_changed"]
    assert all(item["score"] is not None for item in candidate.get("/api/v1/candidate/profile").json()["evidence"])
    candidate.post("/api/v1/candidate/survey",json={"industry":"ИТ","specialization":"backend","grade":"middle","stack":["Python"]})
    assert candidate.post("/api/v1/assessments/start",json={"specialization":"backend","grade":"middle","stack":["Python"]}).status_code == 409


def test_company_practice_is_owned_and_cannot_change_global_category(database):
    employer, candidate, outsider = logged("employer@vector.local"), logged(), logged("employer2@vector.local")
    challenge = employer.post("/api/v1/challenges",json={"title":"Разбор контракта API",
        "description":"Опишите обработку повторного запроса API.","specialization":"backend","skill":"API",
        "public_task":{"type":"text","prompt":"Как обработать конфликт идентификаторов?"}}).json()
    submission = candidate.post(f"/api/v1/challenges/{challenge['id']}/submit",json={"answer":"Проверю payload и верну конфликт."}).json()
    assert submission["result"]["status"] == "awaiting_review" and submission["result"]["score"] is None
    path = f"/api/v1/challenges/{challenge['id']}/submissions/{submission['id']}/review"
    assert outsider.post(path,json={"score":100,"feedback":"Отличное решение"}).status_code == 404
    reviewed = employer.post(path,json={"score":100,"feedback":"Проверено компанией по внутренней рубрике"}).json()
    assert reviewed["result"]["source"] == "COMPANY_REVIEWED" and not reviewed["result"]["category_changed"]
    profile = candidate.get("/api/v1/candidate/profile").json()
    assert profile["confirmed_grade"] is None and not profile["evidence"]


def test_smtp_failures_retry_and_only_successful_delivery_is_marked_delivered(database,monkeypatch):
    import app.auth as auth
    import app.worker as worker
    configured = replace(auth.settings,smtp_host="127.0.0.1",smtp_port=1025)
    monkeypatch.setattr(auth,"settings",configured)
    monkeypatch.setattr(worker,"settings",configured)
    client = TestClient(app)
    response = client.post("/api/v1/auth/register",json={"name":"SMTP participant","email":"smtp@example.invalid",
        "password":PASSWORD,"role":"candidate","consent_processing":True})
    assert response.json()["delivery"] == "queued_smtp"
    def unavailable(*args,**kwargs):
        raise OSError("test SMTP unavailable")
    monkeypatch.setattr(worker.smtplib,"SMTP",unavailable)
    worker.consume_once()
    with database() as db:
        mail = db.scalar(select(MailMessage).where(MailMessage.to == "smtp@example.invalid"))
        assert mail.delivery_status == "retry_pending" and mail.delivered_at is None
        event = db.scalar(select(Outbox).where(Outbox.kind == "email.verification"))
        assert event.status == "pending" and event.attempts == 1
        event.available_at = utcnow() - timedelta(seconds=1)
        db.commit()
    sent = []
    class TestSMTP:
        def __init__(self,*args,**kwargs): pass
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def send_message(self,message): sent.append(message)
    monkeypatch.setattr(worker.smtplib,"SMTP",TestSMTP)
    assert worker.consume_once() == 1 and worker.consume_once() == 0
    assert len(sent) == 1 and sent[0]["To"] == "smtp@example.invalid"
    with database() as db:
        assert db.scalar(select(MailMessage).where(MailMessage.to == "smtp@example.invalid")).delivery_status == "delivered"


def test_ats_transport_signs_real_payload_and_failed_http_cannot_claim_delivery(database,monkeypatch):
    import httpx
    import app.worker as worker
    confirm_fixture(database)
    employer,candidate = logged("employer@vector.local"),logged()
    invitation = invite(employer).json()
    candidate.post(f"/api/v1/invitations/{invitation['id']}/accept")
    monkeypatch.setattr(worker,"settings",replace(worker.settings,ats_webhook_url="http://127.0.0.1:8090/events",ats_webhook_secret="test-only-ats-key"))
    requests = []
    def transport(url,content,headers,**kwargs):
        requests.append((content,headers))
        actual = hmac.new(b"test-only-ats-key",headers["X-Vector-Timestamp"].encode()+b"."+content,hashlib.sha256).hexdigest()
        assert hmac.compare_digest(headers["X-Vector-Signature"],actual)
        assert "PRIVATE-PHONE" not in content.decode() and "contacts" not in content.decode()
        return httpx.Response(503 if len(requests)==1 else 202,request=httpx.Request("POST",url))
    monkeypatch.setattr(worker.httpx,"post",transport)
    worker.consume_once()
    with database() as db:
        assert not db.scalars(select(Delivery)).all()
        event = db.scalar(select(Outbox).where(Outbox.kind == "ats.invitation_accepted"))
        assert event.status == "pending"
        event.available_at = utcnow()-timedelta(seconds=1)
        db.commit()
    assert worker.consume_once() == 1
    assert worker.consume_once() == 0 and len(requests) == 2
    assert employer.get("/api/v1/employer/ats-deliveries").json()["items"][0]["source"] == "signed_webhook"

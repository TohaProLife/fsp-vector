"""Final-release regressions use actual routes and persisted isolated fixtures."""
import io
from datetime import timedelta

import pytest
from pypdf import PdfReader
from sqlalchemy import func, select

from app.common import aware
from app.models import Application, AssessmentAttempt, AuditEvent, Candidate, ContactGrant, utcnow
from test_domain_api import database, confirm_fixture, create_attempt, logged, need_body


@pytest.mark.parametrize("payload,status", [({}, 400), ({"message": "Обсудим роль"}, 400),
    ({"consent_contacts": False}, 400), ({"consent_contacts": "true"}, 422),
    ({"consent_contacts": 1}, 422), ({"consent_contacts": None}, 422)])
def test_application_requires_explicit_contact_permission_before_any_write(database, payload, status):
    confirm_fixture(database)
    candidate, employer = logged(), logged("employer@vector.local")
    vacancy = employer.post("/api/v1/vacancies", json=need_body()).json()
    path = f"/api/v1/vacancies/{vacancy['id']}/apply"
    rejected = candidate.post(path, json=payload)
    assert rejected.status_code == status
    with database() as db:
        assert db.scalar(select(func.count()).select_from(ContactGrant)) == 0
        assert db.scalar(select(func.count()).select_from(Application)) == 0
    assert "contacts" not in employer.get("/api/v1/employer/candidates/candidate-1").json()
    accepted = candidate.post(path, json={"consent_contacts": True})
    assert accepted.status_code == 201
    assert employer.get("/api/v1/applications").json()["items"][0]["candidate"]["contact_authorized"]


@pytest.mark.parametrize("path", ["/profile", "/passport", "/history", "/dashboard"])
def test_history_read_persists_owned_deadline_expiration_without_grade_or_answer_changes(database, path):
    confirm_fixture(database)
    candidate, other = logged(), logged("other@vector.local")
    own, foreign = create_attempt(candidate), create_attempt(other)
    deadline = utcnow() - timedelta(days=2)
    saved_answers = {own["items"][0]["id"]: "Saved draft"}
    with database() as db:
        attempt = db.get(AssessmentAttempt, own["id"])
        attempt.expires_at, attempt.answers = deadline, saved_answers
        db.get(AssessmentAttempt, foreign["id"]).expires_at = deadline
        db.commit()
    response = candidate.get("/api/v1/candidate" + path)
    assert response.status_code == 200
    payload = response.json()
    history = payload["items"] if path == "/history" else payload["profile"]["history"] if path == "/dashboard" else payload["history"]
    assert history[0]["status"] == "expired"
    assert history[0]["finished_at"] == deadline.isoformat()
    with database() as db:
        attempt = db.get(AssessmentAttempt, own["id"])
        assert attempt.status == "expired" and aware(attempt.finished_at) == deadline
        assert attempt.answers == saved_answers and attempt.result is None
        assert db.get(Candidate, "candidate-1").confirmed_grade == "junior"
        assert db.get(AssessmentAttempt, foreign["id"]).status == "in_progress"
    # Opening history after the actual failure window cannot restart that window.
    assert candidate.post("/api/v1/assessments/start", json={"specialization": "backend", "grade": "junior", "stack": ["Python", "SQL"]}).status_code == 201


def test_unicode_pdf_distinguishes_synthetic_real_revoked_and_company_evidence(database):
    confirm_fixture(database)
    candidate = logged()
    with database() as db:
        profile = db.get(Candidate, "candidate-1")
        profile.confirmed_categories = {"backend": {**profile.confirmed_categories["backend"], "source": "SYNTHETIC_SEED"}}
        profile.evidence = [
            {"skill": "SYNTHETIC_SQL", "source": "ASSESSMENT_VERIFIED", "status": "verified", "origin": "SYNTHETIC_SEED"},
            {"skill": "REAL_API", "source": "ASSESSMENT_VERIFIED", "status": "verified"},
            {"skill": "REVOKED_HTTP", "source": "ASSESSMENT_VERIFIED", "status": "revoked"},
            {"skill": "COMPANY_SQL", "source": "NEED_PRACTICE_OBSERVED", "status": "observed", "scope": {"global_grade": False}},
            {"skill": "DEMO_FSP", "source": "FSP_DEMO_CONFIRMED", "is_demo": True},
        ]
        db.commit()
    result = candidate.get("/api/v1/candidate/profile.pdf")
    assert result.status_code == 200 and result.headers["cache-control"] == "no-store"
    text = " ".join("\n".join(page.extract_text() for page in PdfReader(io.BytesIO(result.content)).pages).split())
    assert "Категория в паспорте: junior · синтетический пример" in text
    assert "SYNTHETIC_SQL · Синтетический пример" in text
    assert "REAL_API · Экзамен · подтверждено" in text
    assert "REVOKED_HTTP · Экзамен · статус не подтверждён · свидетельство отозвано" in text
    assert "COMPANY_SQL · Практика компании · наблюдение" in text
    assert "не присваивает глобальный грейд" in text
    assert "DEMO_FSP · Демонстрационная проверка" in text
    assert logged("employer@vector.local").get("/api/v1/candidate/profile.pdf").status_code == 403


def test_paginated_attempt_and_survey_history_reaches_old_records_and_retains_owned_snapshots(database):
    candidate, other = logged(), logged("other@vector.local")
    own, foreign = create_attempt(candidate), create_attempt(other)
    assert candidate.post(f"/api/v1/assessments/{own['id']}/submit", json={"answers": {}}).status_code == 200
    now = utcnow()
    # Only this isolated test DB gets historical synthetic records. No fixture
    # changes a user's category or represents a real successful assessment.
    with database() as db:
        template = db.get(AssessmentAttempt, own["id"])
        for index in range(35):
            when = now - timedelta(days=index + 1)
            db.add(AssessmentAttempt(id=f"history-fixture-{index:02}", candidate_id="candidate-1",
                specialization="backend", grade="junior", stack=["Python", "SQL"], status="completed", demo=True,
                started_at=when, finished_at=when + timedelta(minutes=10), expires_at=when + timedelta(minutes=40),
                private_form=template.private_form, answers={},
                result={**template.result, "attempt_id":f"history-fixture-{index:02}", "demo":True, "fixture_id":index}))
            db.add(AuditEvent(id=f"survey-fixture-{index:02}", account_id="account-1", action="survey.completed",
                created_at=when, data={"taxonomy_version":"fixture-taxonomy", "answers":{"grade":"junior", "fixture_id":index}}))
        db.add(AuditEvent(id="foreign-survey", account_id="account-2", action="survey.completed",
            data={"taxonomy_version":"foreign-private-marker", "answers":{"private_marker":"FOREIGN"}}))
        db.commit()
    for path in ["/api/v1/candidate/history", "/api/v1/candidate/survey-history"]:
        first = candidate.get(path).json()
        from app.contracts import AssessmentHistoryPage, SurveyHistoryPage
        contract = AssessmentHistoryPage if path.endswith("/history") else SurveyHistoryPage
        contract.model_validate(first)
        assert first["total"] == 36 and first["page"] == 1 and first["page_size"] == 30 and len(first["items"]) == 30
        second = candidate.get(path, params={"page":2}).json()
        contract.model_validate(second)
        assert second["total"] == 36 and second["page"] == 2 and second["page_size"] == 30 and len(second["items"]) == 6
        ids = [entry["id"] for entry in first["items"] + second["items"]]
        assert len(set(ids)) == 36 and foreign["id"] not in ids and "foreign-survey" not in ids
        tail = second["items"][-1]
        if path.endswith("/history"):
            assert tail["result"]["fixture_id"] == 34
        else:
            assert tail["answers"]["fixture_id"] == 34
            assert tail["taxonomy_version"] == "fixture-taxonomy" and tail["snapshot_available"]
        custom = candidate.get(path, params={"page_size":7,"page":2}).json()
        assert custom["items"] == first["items"][7:14] and custom["total"] == 36
        beyond = candidate.get(path, params={"page":99}).json()
        assert beyond["items"] == [] and beyond["total"] == 36
        foreign_history = other.get(path).json()
        assert not any(entry["id"] in ids for entry in foreign_history["items"])
    assert len(candidate.get("/api/v1/candidate/profile").json()["history"]) == 30


@pytest.mark.parametrize("path", ["/api/v1/candidate/history", "/api/v1/candidate/survey-history"])
@pytest.mark.parametrize("params", [{"page":0}, {"page":-1}, {"page_size":0}, {"page_size":101}])
def test_history_pagination_is_bounded_on_the_server(database, path, params):
    assert logged().get(path, params=params).status_code == 422

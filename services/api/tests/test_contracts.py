"""Validate reusable OpenAPI contracts against real persisted route responses."""
import json
import importlib
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from app.main import app
from app import contracts as dto
from evaluation.reference_solvers import reference_answer
from test_domain_api import database, logged, confirm_fixture, create_attempt, invite, need_body, reference_answers


def checked(response, model, status=200):
    assert response.status_code == status, response.text
    payload = response.json()
    model.model_validate(payload)
    return payload


def test_openapi_all_methods_have_response_security_and_resolvable_refs():
    schema = app.openapi()
    assert len(schema["paths"]) >= 73
    assert schema["components"]["securitySchemes"]["cookieAuth"] == {
        "type": "apiKey", "in": "cookie", "name": "vector_session",
        "description": schema["components"]["securitySchemes"]["cookieAuth"]["description"]}
    for path, item in schema["paths"].items():
        for method, operation in item.items():
            assert "security" in operation, (path, method)
            assert operation["responses"]
            for code, response in operation["responses"].items():
                if code.startswith("2"):
                    assert response["content"], (path, method, code)
                    assert all(media["schema"] for media in response["content"].values())
            if operation["security"] and method in {"post", "put", "patch", "delete"}:
                assert any(parameter["name"] == "X-CSRF-Token" and parameter["required"] for parameter in operation["parameters"])
    for path, method in [("/api/v1/auth/register", "post"), ("/api/v1/auth/login", "post"),
            ("/api/v1/health", "get"), ("/ready", "get"), ("/api/v1/assessments/catalog", "get"),
            ("/api/v1/auth/oidc/status", "get")]:
        assert schema["paths"][path][method]["security"] == []
    candidate = schema["paths"]["/api/v1/candidate/profile"]["get"]
    assert candidate["x-required-role"] == "candidate" and candidate["x-processing-consent-required"]
    employer = schema["paths"]["/api/v1/employer/matches"]["post"]
    assert employer["x-required-role"] == "employer"
    assert "302" in schema["paths"]["/api/v1/auth/oidc/login"]["get"]["responses"]
    assert "application/pdf" in schema["paths"]["/api/v1/candidate/profile.pdf"]["get"]["responses"]["200"]["content"]
    assert "text/event-stream" in schema["paths"]["/api/v1/events"]["get"]["responses"]["200"]["content"]
    def walk(value):
        if isinstance(value, dict):
            if "$ref" in value:
                ref = value["$ref"]
                assert ref.startswith("#/"), ref
                target = schema
                for segment in ref[2:].split("/"):
                    target = target[segment.replace("~1", "/").replace("~0", "~")]
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(schema)


def test_core_contracts_match_actual_category_matching_invitation_and_scoped_practice(database):
    candidate, employer = logged(), logged("employer@vector.local")
    checked(candidate.get("/api/v1/auth/me"), dto.Me)
    checked(candidate.get("/api/v1/candidate/profile"), dto.OwnProfile)
    attempt = create_attempt(candidate)
    dto.AssessmentAttempt.model_validate(attempt)
    completed = checked(candidate.post(f"/api/v1/assessments/{attempt['id']}/submit",
        json={"answers": reference_answers(database, attempt["id"])}), dto.AssessmentAttempt)
    assert completed["result"]["certifies_global_category"] and completed["result"]["category_changed"]
    profile = checked(candidate.get("/api/v1/candidate/profile"), dto.OwnProfile)
    assert profile["history"] and profile["survey_history"]
    checked(candidate.get("/api/v1/assessments/availability"), dto.AssessmentAvailability)
    checked(candidate.post("/api/v1/candidate/publication", json={"published": True, "consent_publication": True}), dto.OwnProfile)
    need_response = employer.post("/api/v1/employer/needs", json=need_body(skills=["API"]))
    assert need_response.status_code == 201, need_response.text
    need = need_response.json()
    checked(employer.get(f"/api/v1/employer/needs/{need['id']}/assessment-blueprint"), dto.NeedBlueprint)
    match = checked(employer.post("/api/v1/employer/matches", json={"need_id": need["id"]}), dto.Match, 201)
    assert match["items"] and "contacts" not in match["items"][0]["candidate"]
    checked(employer.get(f"/api/v1/employer/matches/{match['id']}"), dto.Match)
    checked(employer.post(f"/api/v1/employer/matches/{match['id']}/refine", json={"filters": {}}), dto.Match, 201)
    invitation = checked(invite(employer, need_id=need["id"]), dto.Invitation, 201)
    checked(candidate.get(f"/api/v1/invitations/{invitation['id']}"), dto.Invitation)
    checked(candidate.get("/api/v1/invitations"), dto.Invitations)
    accepted = checked(candidate.post(f"/api/v1/invitations/{invitation['id']}/accept"), dto.Invitation)
    scoped = checked(candidate.post("/api/v1/assessments/need-start", json={"invitation_id": invitation["id"]}), dto.AssessmentAttempt, 201)
    result = checked(candidate.post(f"/api/v1/assessments/{scoped['id']}/submit", json={
        "answers": {item["id"]: reference_answer(item) for item in scoped["items"]}}), dto.AssessmentAttempt)
    assert not result["result"]["certifies_global_category"] and not result["result"]["category_changed"]
    grant = checked(candidate.get("/api/v1/candidate/profile"), dto.OwnProfile)["contact_grants"][0]
    dto.ContactGrant.model_validate(grant)
    checked(candidate.post(f"/api/v1/candidate/contact-grants/{accepted['contact_grant_id']}/revoke"), dto.RevokedGrant)
    checked(employer.get(f"/api/v1/employer/candidates/{profile['id']}"), dto.CandidateProfile)
    candidate.post("/api/v1/auth/consents", json={"consent_processing": False})
    hidden = checked(employer.get(f"/api/v1/invitations/{invitation['id']}"), dto.Invitation)
    dto.UnavailableCandidate.model_validate(hidden["candidate"])
    assert "contacts" not in hidden["candidate"]


def test_weekly_contracts_match_real_objective_and_manual_results(database):
    candidate, employer = logged(), logged("employer@vector.local")
    weekly = checked(candidate.get("/api/v1/challenges/weekly"), dto.WeeklyPractice)
    task = weekly["challenge"]
    checked(candidate.get(f"/api/v1/challenges/{task['id']}"), dto.Challenge)
    solved = checked(candidate.post(f"/api/v1/challenges/{task['id']}/submit", json={
        "answer": reference_answer(task["public_task"])}), dto.PracticeSubmission, 201)
    assert solved["result"]["passed"]
    assert checked(candidate.get("/api/v1/challenges/weekly"), dto.WeeklyPractice)["completed"]
    manual = checked(employer.post("/api/v1/challenges", json={"title": "Контракт API", "description": "Объясните идемпотентность API",
        "specialization": "backend", "skill": "API", "public_task": {"prompt": "Как хранить event_id?"}}), dto.Challenge, 201)
    awaiting = checked(candidate.post(f"/api/v1/challenges/{manual['id']}/submit", json={
        "answer": "Уникальность event_id и транзакция"}), dto.PracticeSubmission, 201)
    assert awaiting["result"]["score"] is None and awaiting["result"]["passed"] is None


def test_problem_details_contract_matches_auth_rights_validation_state_and_size(database):
    anonymous, candidate, employer = TestClient(app), logged(), logged("employer@vector.local")
    checked(anonymous.get("/api/v1/candidate/profile"), dto.ProblemDetails, 401)
    checked(employer.get("/api/v1/candidate/profile"), dto.ProblemDetails, 403)
    checked(candidate.patch("/api/v1/candidate/profile", json={"confirmed_grade": "senior"}), dto.ProblemDetails, 422)
    checked(candidate.post("/api/v1/assessments/start", json={"specialization": "backend", "grade": "junior"}), dto.ProblemDetails, 409)
    checked(candidate.get("/api/v1/assessments/missing"), dto.ProblemDetails, 404)
    checked(candidate.post("/api/v1/candidate/resume-import", files={"file": ("a.txt", b"not pdf", "text/plain")}), dto.ProblemDetails, 415)
    candidate.headers.pop("X-CSRF-Token")
    rejected = checked(candidate.post("/api/v1/candidate/publication", json={"published": True}), dto.ProblemDetails, 403)
    assert rejected["code"] == "CSRF_REJECTED"
    large = checked(anonymous.post("/api/v1/auth/login", content=b"x" * (4 * 1024 * 1024 + 1)), dto.ProblemDetails, 413)
    assert large["request_id"] is None and large["status"] == 413  # Rejects before route/PII parsing.
    assert "PRIVATE-PHONE" not in json.dumps(rejected)


def test_problem_details_services_fail_sanitized_with_actual_500_and_503(database, monkeypatch):
    main = importlib.import_module("app.main")
    class UnavailableDatabase:
        def connect(self):
            raise OperationalError("select", {}, RuntimeError("connection internal-secret-test-value"))
    monkeypatch.setattr(main, "engine", UnavailableDatabase())
    client = TestClient(app, raise_server_exceptions=False)
    unavailable = checked(client.get("/ready"), dto.ProblemDetails, 503)
    assert unavailable["code"] == "DATABASE_UNAVAILABLE" and unavailable["request_id"]
    class UnexpectedDatabase:
        def connect(self):
            raise RuntimeError("internal-secret-test-value")
    monkeypatch.setattr(main, "engine", UnexpectedDatabase())
    unexpected = checked(client.get("/ready"), dto.ProblemDetails, 500)
    assert unexpected["code"] == "INTERNAL_ERROR" and unexpected["request_id"]
    assert "internal-secret-test-value" not in json.dumps([unavailable, unexpected])

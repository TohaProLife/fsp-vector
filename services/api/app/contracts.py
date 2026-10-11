"""Explicit reusable response contracts and the actual cookie/Problem API boundary.

Models describe stable fields; extra versioned engine/domain fields remain legal.
They do not run an alternative grading path or strip actual endpoint responses.
"""
from datetime import datetime
from typing import Literal
from fastapi.openapi.utils import get_openapi
from fastapi.routing import APIRoute, iter_route_contexts
from pydantic import BaseModel, ConfigDict, Field, JsonValue

JsonObject = dict[str, JsonValue]


class Contract(BaseModel):
    model_config = ConfigDict(extra="allow")


class ProblemDetails(Contract):
    type: str
    title: str
    status: int = Field(ge=400, le=599)
    detail: str
    code: str
    request_id: str | None
    errors: list[JsonObject] | None = None


class GenericObject(Contract):
    """Dynamic domain object: fields are documented by the owning route/contract."""


class Me(Contract):
    id: str
    name: str
    email: str
    role: Literal["candidate", "employer"]
    email_verified: bool
    consent_processing: bool
    csrf_token: str
    candidate_id: str | None
    company_id: str | None


class AssessmentReviewIssue(Contract):
    item_id: str | None
    kind: Literal["missing", "format", "limit"]
    detail: str


class AssessmentReview(Contract):
    """Public format review, never a correctness/grade preview or permission grant."""
    answered: int = Field(ge=0)
    total: int = Field(ge=0)
    structural_ready: bool
    issues: list[AssessmentReviewIssue]
    public_form_sha256: str | None
    saved_answers_sha256: str | None
    prospective_answers_sha256: str | None
    review_token: str | None
    limitations: list[str]


class EvaluationProvenance(Contract):
    status: Literal["verified", "unavailable"]
    checked_files: int = Field(ge=0)
    report_sha256: str | None
    stability_sha256: str | None


class EvaluationSummary(Contract):
    status: Literal["ready", "unavailable", "integrity_mismatch", "source_mismatch", "invalid_artifact"]
    reason: str | None
    synthetic: Literal[True]
    human_validity: Literal["not_measured"]
    generated_at: datetime | None
    provenance: EvaluationProvenance
    measurements: JsonObject | None
    notice: str


class QualitySummary(Contract):
    environment: str
    calibration_status: str
    human_pilot: JsonObject
    evaluation: EvaluationSummary
    runtime: JsonObject
    counts: dict[str, int]
    measurement_policy: str


class AssessmentResult(Contract):
    score: float = Field(ge=0, le=100)
    passed: bool
    competencies: dict[str, float]
    practice_score: float = Field(ge=0, le=100)
    confirmed_grade: str | None
    category_changed: bool
    attempt_id: str
    demo: bool
    feedback: list[JsonObject]
    calibration_status: str
    category_change_allowed: bool | None = None
    certifies_global_category: bool | None = None
    scope: str | None = None
    global_confirmed_grade: str | None = None
    context: JsonObject | None = None
    limitations: list[str] | None = None


class AssessmentAttempt(Contract):
    id: str
    status: str
    specialization: str
    grade: str
    stack: list[str]
    demo: bool
    expires_at: datetime
    started_at: datetime
    items: list[JsonObject]
    answers: JsonObject
    result: AssessmentResult | None
    policy: JsonObject
    blueprint_version: str | None
    calibration_status: str
    tested_skills: list[str] | None
    unmeasured_requested_skills: list[str] | None
    route: str | None
    scope: str
    context: JsonObject | None
    certifies_global_category: bool


class AssessmentHistory(Contract):
    id: str
    specialization: str
    grade: str
    status: str
    demo: bool
    started_at: datetime
    finished_at: datetime | None
    result: AssessmentResult | None
    score: float | None
    passed: bool
    scope: str
    context: JsonObject | None


class SurveyHistory(Contract):
    id: str
    created_at: datetime
    taxonomy_version: str | None
    answers: JsonObject | None
    snapshot_available: bool


class AssessmentHistoryPage(Contract):
    items: list[AssessmentHistory]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)


class SurveyHistoryPage(Contract):
    items: list[SurveyHistory]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)


class ContactGrant(Contract):
    id: str
    company_id: str
    company_name: str
    source: str
    active: bool
    created_at: datetime
    revoked_at: datetime | None


class RevokedGrant(Contract):
    id: str
    active: Literal[False]
    revoked_at: datetime
    message: str


class CandidateProfile(Contract):
    id: str
    alias: str
    name: str
    title: str
    bio: str
    city: str
    specialization: str | None
    declared_grade: str | None
    confirmed_grade: str | None
    category: str | None
    score: float | None
    skills: list[str]
    preferences: JsonObject
    published: bool
    evidence: list[JsonObject]
    fsp: JsonObject
    achievements: list[JsonObject]
    assessment_at: datetime | None
    source: str
    updated_at: datetime
    contact_authorized: bool
    contacts: dict[str, str] | None = None


class OwnProfile(CandidateProfile):
    survey: JsonObject
    history: list[AssessmentHistory]
    confirmed_categories: JsonObject
    survey_history: list[SurveyHistory]
    contact_grants: list[ContactGrant]
    blocked_companies: list[JsonObject]


class UnavailableCandidate(Contract):
    id: str
    alias: str
    name: str
    published: Literal[False]
    contact_authorized: Literal[False]
    profile_available: Literal[False]


class InvitationMessage(Contract):
    id: str
    text: str
    author_role: Literal["candidate", "employer"]
    created_at: datetime


class Invitation(Contract):
    id: str
    candidate_id: str
    company_id: str
    need_id: str | None
    vacancy_id: str | None
    title: str
    message: str
    salary_from: int = Field(gt=0)
    salary_to: int = Field(gt=0)
    work_format: str
    employment: str
    contact: str
    status: str
    company: JsonObject
    viewed_at: datetime | None
    candidate: CandidateProfile | UnavailableCandidate
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None
    contact_grant_id: str | None
    contacts_open: bool
    messages: list[InvitationMessage]


class Invitations(Contract):
    items: list[Invitation]
    total: int = Field(ge=0)


class MatchFeature(Contract):
    value: float
    weight: float
    points: float


class MatchItem(Contract):
    score: float
    breakdown: dict[str, MatchFeature]
    reasons: list[JsonObject]
    gaps: list[JsonObject]
    semantic_status: str | None
    candidate: CandidateProfile | UnavailableCandidate


class Match(Contract):
    id: str
    need_id: str
    parent_id: str | None
    algorithm_version: str
    items: list[MatchItem]
    total: int = Field(ge=0)
    filters: JsonObject
    need: JsonObject
    created_at: datetime
    score_kind: Literal["ranking_index_not_probability"]


class NeedCompetency(Contract):
    id: str
    label: str
    priority: Literal["required", "preferred", "common_blueprint"]
    requested_skills: list[str]
    measurable_skills: list[str]
    item_count: int


class TestedSlice(Contract):
    skill: str
    scope: str
    certifies_global_grade: Literal[False]


class NeedBlueprint(Contract):
    need_id: str
    context_version: str
    scope: Literal["employer_need_practice"]
    need_snapshot_sha256: str
    specialization: str
    grade: str
    category_change: Literal[False]
    category_changes: Literal[False]
    item_count: int
    competencies: list[NeedCompetency]
    required_skills: list[str]
    requested_skills: list[str]
    tested_skills: list[str]
    unmeasured_skills: list[str]
    tested_slices: list[TestedSlice]
    blueprint_rule: str
    limitations: list[str]


class PracticeResult(Contract):
    status: str
    score: float | None
    passed: bool | None
    feedback: str
    category_changed: Literal[False]


class Challenge(Contract):
    id: str
    title: str
    description: str
    specialization: str
    skill: str
    public_task: JsonObject
    company: JsonObject | None
    published: bool
    created_at: datetime
    category_changes: Literal[False]
    grading: str
    last_result: PracticeResult | None = None


class PracticeSubmission(Contract):
    id: str
    challenge_id: str
    result: PracticeResult
    created_at: datetime


class WeeklyPractice(Contract):
    week_id: str
    opens_at: datetime
    next_week_at: datetime
    timezone: Literal["UTC"]
    challenge: Challenge
    submission: PracticeSubmission | None
    completed: bool
    retry_at: datetime | None
    policy: JsonObject


class GradeAvailability(Contract):
    grade: str
    allowed: bool
    next_allowed_at: datetime | None
    reason: str
    confirmed_grade: str | None
    policy_version: str


class ActiveAttempt(Contract):
    id: str
    specialization: str
    grade: str
    scope: str
    expires_at: datetime


class AssessmentAvailability(Contract):
    specialization: str
    items: list[GradeAvailability]
    active_attempt: ActiveAttempt | None
    server_time: datetime


CORE_RESPONSES = {
    ("/api/v1/quality/summary", "get"): QualitySummary,
    ("/api/v1/assessments/{attempt_id}/review", "post"): AssessmentReview,
    ("/api/v1/auth/login", "post"): Me,
    ("/api/v1/auth/me", "get"): Me,
    ("/api/v1/candidate/profile", "get"): OwnProfile,
    ("/api/v1/candidate/profile", "patch"): OwnProfile,
    ("/api/v1/candidate/survey", "post"): OwnProfile,
    ("/api/v1/candidate/publication", "post"): OwnProfile,
    ("/api/v1/candidate/passport", "get"): OwnProfile,
    ("/api/v1/candidate/history", "get"): AssessmentHistoryPage,
    ("/api/v1/candidate/survey-history", "get"): SurveyHistoryPage,
    ("/api/v1/candidate/contact-grants/{grant_id}/revoke", "post"): RevokedGrant,
    ("/api/v1/assessments/start", "post"): AssessmentAttempt,
    ("/api/v1/assessments/need-start", "post"): AssessmentAttempt,
    ("/api/v1/assessments/{attempt_id}", "get"): AssessmentAttempt,
    ("/api/v1/assessments/{attempt_id}/submit", "post"): AssessmentAttempt,
    ("/api/v1/assessments/availability", "get"): AssessmentAvailability,
    ("/api/v1/employer/candidates/{candidate_id}", "get"): CandidateProfile,
    ("/api/v1/employer/matches", "post"): Match,
    ("/api/v1/employer/matches/{match_id}", "get"): Match,
    ("/api/v1/employer/matches/{match_id}/refine", "post"): Match,
    ("/api/v1/employer/needs/{need_id}/assessment-blueprint", "get"): NeedBlueprint,
    ("/api/v1/invitations", "get"): Invitations,
    ("/api/v1/invitations", "post"): Invitation,
    ("/api/v1/invitations/{invitation_id}", "get"): Invitation,
    ("/api/v1/invitations/{invitation_id}/accept", "post"): Invitation,
    ("/api/v1/invitations/{invitation_id}/decline", "post"): Invitation,
    ("/api/v1/invitations/{invitation_id}/withdraw", "post"): Invitation,
    ("/api/v1/invitations/{invitation_id}/messages", "post"): Invitation,
    ("/api/v1/challenges/weekly", "get"): WeeklyPractice,
    ("/api/v1/challenges/{challenge_id}", "get"): Challenge,
    ("/api/v1/challenges", "post"): Challenge,
    ("/api/v1/challenges/{challenge_id}/submit", "post"): PracticeSubmission,
}


def dependency_calls(dependant):
    result = {dependant.call}
    for child in dependant.dependencies:
        result.update(dependency_calls(child))
    return result


def install_openapi(app):
    """Documentation only: normal endpoint/domain authorization remains authority."""
    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        from .auth import current_user, verified_user, candidate_user, employer_user
        schema = get_openapi(title=app.title, version=app.version, description=app.description, routes=app.routes)
        components = schema.setdefault("components", {})
        schemas = components.setdefault("schemas", {})
        for model in {GenericObject, ProblemDetails, *CORE_RESPONSES.values()}:
            definition = model.model_json_schema(ref_template="#/components/schemas/{model}")
            schemas.update(definition.pop("$defs", {}))
            schemas[model.__name__] = definition
        components.setdefault("securitySchemes", {})["cookieAuth"] = {
            "type": "apiKey", "in": "cookie", "name": "vector_session",
            "description": "Opaque HttpOnly session. Verified workspaces also require email and processing consent. Mutations require X-CSRF-Token from /auth/me; provider tokens are never returned to the browser."}
        error = {"$ref": "#/components/schemas/ProblemDetails"}
        # FastAPI's pinned release preserves included routers as lazy branches.
        # Use the same effective route traversal as its OpenAPI generator.
        for route in iter_route_contexts(app.routes):
            if not isinstance(route.original_route, APIRoute) or not route.include_in_schema:
                continue
            calls = dependency_calls(route.dependant)
            for method in route.methods:
                operation = schema.get("paths", {}).get(route.path, {}).get(method.lower())
                if not operation:
                    continue
                authenticated = current_user in calls
                operation["security"] = [{"cookieAuth": []}] if authenticated else []
                if verified_user in calls:
                    operation["x-email-verification-required"] = True
                    operation["x-processing-consent-required"] = True
                if candidate_user in calls or employer_user in calls:
                    operation["x-required-role"] = "candidate" if candidate_user in calls else "employer"
                mutating = method not in {"GET", "HEAD", "OPTIONS"}
                if authenticated and mutating:
                    operation.setdefault("parameters", []).append({"name": "X-CSRF-Token", "in": "header", "required": True,
                        "description": "Session-bound token from GET /api/v1/auth/me. A mismatched/missing token rejects the mutation.",
                        "schema": {"type": "string"}})
                status = str(route.status_code or 200)
                response = operation.setdefault("responses", {}).setdefault(status, {"description": "Successful response"})
                if route.path == "/api/v1/candidate/profile.pdf":
                    response["content"] = {"application/pdf": {"schema": {"type": "string", "format": "binary"}}}
                elif route.path == "/api/v1/events":
                    response["content"] = {"text/event-stream": {"schema": {"type": "string"},
                        "example": 'event: notification\ndata: {"id":"notification-id","kind":"invitation.received"}\n\n'}}
                elif route.path in {"/api/v1/auth/oidc/login", "/api/v1/auth/oidc/callback"}:
                    operation["responses"].pop(status, None)
                    operation["responses"]["302"] = {"description": "Redirect through the configured OIDC Authorization Code + PKCE flow",
                        "headers": {"Location": {"schema": {"type": "string"}}}}
                else:
                    model = CORE_RESPONSES.get((route.path, method.lower()), GenericObject)
                    response["content"] = {"application/json": {"schema": {"$ref": f"#/components/schemas/{model.__name__}"}}}
                errors = {400, 403, 404, 422, 500, 503}
                if authenticated:
                    errors.add(401)
                if mutating:
                    errors.update({409, 429})
                if method in {"POST", "PUT", "PATCH"}:
                    errors.add(413)
                if route.path == "/api/v1/auth/login":
                    errors.update({401, 429})
                if route.path == "/api/v1/candidate/resume-import":
                    errors.add(415)
                for code in errors:
                    operation["responses"][str(code)] = {"description": "Problem Details: domain validation, rights, state, limits or sanitized service failure; the actual code explains the reason.",
                        "content": {"application/json": {"schema": error, "example": {
                            "type": "urn:vector:problem:example", "title": "Действие не выполнено", "status": code,
                            "detail": "См. код и условия операции.", "code": "DOMAIN_PROBLEM", "request_id": "request-uuid"}}}}
                    if code == 413:
                        operation["responses"][str(code)]["content"]["application/problem+json"] = {"schema": error}
                if route.path == "/api/v1/auth/demo-mailbox":
                    operation["x-local-demo-only"] = True
        app.openapi_schema = schema
        return schema
    app.openapi = custom_openapi
    app.openapi_schema = None

from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


def utcnow():
    return datetime.now(timezone.utc)


def new_id():
    return str(uuid4())


class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20))
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BrowserSession(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    csrf_token: Mapped[str] = mapped_column(String(100))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class LoginFailure(Base):
    __tablename__ = "login_failures"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    identity_bucket: Mapped[str] = mapped_column(String(64), index=True)
    network_bucket: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class EmailVerification(Base):
    __tablename__ = "email_verifications"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used: Mapped[bool] = mapped_column(Boolean, default=False)


class MailMessage(Base):
    __tablename__ = "mail_messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    to: Mapped[str] = mapped_column(String(254), index=True)
    subject: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    verification_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    delivery_status: Mapped[str] = mapped_column(String(30), default="queued")
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivery_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class Candidate(Base):
    __tablename__ = "candidates"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), unique=True)
    alias: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(200), default="")
    bio: Mapped[str] = mapped_column(Text, default="")
    city: Mapped[str] = mapped_column(String(120), default="")
    specialization: Mapped[str | None] = mapped_column(String(40), nullable=True)
    declared_grade: Mapped[str | None] = mapped_column(String(20), nullable=True)
    confirmed_grade: Mapped[str | None] = mapped_column(String(20), nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    skills: Mapped[list] = mapped_column(JSON, default=list)
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)
    contacts: Mapped[dict] = mapped_column(JSON, default=dict)
    survey: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    confirmed_categories: Mapped[dict] = mapped_column(JSON, default=dict)
    fsp: Mapped[dict] = mapped_column(JSON, default=lambda: {"status": "not_linked", "achievements": []})
    published: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    assessment_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fixture: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Company(Base):
    __tablename__ = "companies"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), unique=True)
    name: Mapped[str] = mapped_column(String(200), default="Новая компания")
    description: Mapped[str] = mapped_column(Text, default="")
    industry: Mapped[str] = mapped_column(String(120), default="ИТ")
    city: Mapped[str] = mapped_column(String(120), default="")
    website: Mapped[str] = mapped_column(String(300), default="")
    contact: Mapped[str] = mapped_column(String(300), default="")
    team: Mapped[str] = mapped_column(Text, default="")


class Consent(Base):
    __tablename__ = "consents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[str] = mapped_column(String(40))
    granted: Mapped[bool] = mapped_column(Boolean)
    version: Mapped[str] = mapped_column(String(30), default="2026-10-07")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AssessmentAttempt(Base):
    __tablename__ = "assessment_attempts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    specialization: Mapped[str] = mapped_column(String(40))
    grade: Mapped[str] = mapped_column(String(20))
    stack: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(30), default="in_progress")
    demo: Mapped[bool] = mapped_column(Boolean, default=False)
    private_form: Mapped[dict] = mapped_column(JSON)
    answers: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Need(Base):
    __tablename__ = "needs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class MatchRun(Base):
    __tablename__ = "match_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    need_id: Mapped[str] = mapped_column(ForeignKey("needs.id", ondelete="CASCADE"))
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("match_runs.id"), nullable=True)
    filters: Mapped[dict] = mapped_column(JSON, default=dict)
    algorithm_version: Mapped[str] = mapped_column(String(80), default="vector-matching-v1")
    results: Mapped[list] = mapped_column(JSON, default=list)
    need_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Invitation(Base):
    __tablename__ = "invitations"
    __table_args__ = (CheckConstraint("salary_from > 0 AND salary_to >= salary_from", name="ck_invitation_salary"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    need_id: Mapped[str | None] = mapped_column(ForeignKey("needs.id"), nullable=True)
    vacancy_id: Mapped[str | None] = mapped_column(ForeignKey("vacancies.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    salary_from: Mapped[int] = mapped_column(Integer)
    salary_to: Mapped[int] = mapped_column(Integer)
    data: Mapped[dict] = mapped_column(JSON)
    company_snapshot: Mapped[dict] = mapped_column(JSON)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ContactGrant(Base):
    __tablename__ = "contact_grants"
    __table_args__ = (UniqueConstraint("company_id", "candidate_id", name="uq_contact_grant_scope"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    invitation_id: Mapped[str | None] = mapped_column(ForeignKey("invitations.id"), nullable=True)
    source: Mapped[str] = mapped_column(String(30), default="invitation")
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class InvitationMessage(Base):
    __tablename__ = "invitation_messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    invitation_id: Mapped[str] = mapped_column(ForeignKey("invitations.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Vacancy(Base):
    __tablename__ = "vacancies"
    __table_args__ = (CheckConstraint("NOT published OR (salary_from > 0 AND salary_to >= salary_from)", name="ck_vacancy_salary"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    data: Mapped[dict] = mapped_column(JSON)
    published: Mapped[bool] = mapped_column(Boolean, default=True)
    salary_from: Mapped[int] = mapped_column(Integer)
    salary_to: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("vacancy_id", "candidate_id", name="uq_application"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    vacancy_id: Mapped[str] = mapped_column(ForeignKey("vacancies.id", ondelete="CASCADE"), index=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="new")
    message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Challenge(Base):
    __tablename__ = "challenges"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    company_id: Mapped[str | None] = mapped_column(ForeignKey("companies.id"), nullable=True)
    data: Mapped[dict] = mapped_column(JSON)
    rubric: Mapped[dict] = mapped_column(JSON, default=dict)
    published: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChallengeSubmission(Base):
    __tablename__ = "challenge_submissions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    challenge_id: Mapped[str] = mapped_column(ForeignKey("challenges.id", ondelete="CASCADE"))
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"))
    answer: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(60))
    title: Mapped[str] = mapped_column(String(200))
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Outbox(Base):
    __tablename__ = "outbox"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(60))
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class Delivery(Base):
    __tablename__ = "integration_deliveries"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_id: Mapped[str] = mapped_column(ForeignKey("outbox.id"), unique=True)
    destination: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FspRecord(Base):
    __tablename__ = "fsp_demo_records"
    fsp_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    email: Mapped[str] = mapped_column(String(254))
    proof_hash: Mapped[str] = mapped_column(String(64))
    achievements: Mapped[list] = mapped_column(JSON, default=list)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    account_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CompanyBlock(Base):
    __tablename__ = "company_blocks"
    __table_args__ = (UniqueConstraint("candidate_id", "company_id", name="uq_company_block"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"))
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    invitation_id: Mapped[str] = mapped_column(ForeignKey("invitations.id"))
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="received")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

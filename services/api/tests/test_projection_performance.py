"""Bulk projection SQL bounds must preserve consent and company isolation."""
from contextlib import contextmanager
from datetime import timedelta

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.common import candidate_accessible, candidate_projection, has_grant, prime_projection_access
from app.db import Base
from app.models import Account, Candidate, Company, CompanyBlock, Consent, ContactGrant, utcnow


@pytest.fixture()
def projection_database():
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as db:
        for company_id in ("company-A", "company-B"):
            db.add(Account(id=f"account-{company_id}", name=company_id,
                           email=f"{company_id}@example.invalid", password_hash="not-a-login",
                           role="employer", email_verified=True))
        for index in range(24):
            db.add(Account(id=f"a{index:02}", name=f"Private name {index}",
                           email=f"person{index}@example.invalid", password_hash="not-a-login",
                           role="candidate", email_verified=True))
        db.flush()
        for company_id in ("company-A", "company-B"):
            db.add(Company(id=company_id, account_id=f"account-{company_id}", name=company_id))
        for index in range(24):
            db.add(Candidate(id=f"c{index:02}", account_id=f"a{index:02}", alias=f"Alias {index}",
                             published=True, confirmed_grade="junior", specialization="backend",
                             title="Backend", bio=f"Private biography {index}",
                             contacts={"phone": f"private-phone-{index}"}))
            db.add(Consent(account_id=f"a{index:02}", purpose="processing", granted=True,
                           created_at=utcnow() - timedelta(hours=1)))
        db.flush()
        for index in range(0, 24, 3):
            db.add(ContactGrant(candidate_id=f"c{index:02}", company_id="company-A"))
        db.commit()
    yield sessions
    engine.dispose()


@contextmanager
def select_counter(engine):
    statements = []

    def count(_, __, statement, ___, ____, _____):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", count)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", count)


def population(db):
    return db.scalars(select(Candidate).order_by(Candidate.id)).all()


def assert_unavailable(card):
    assert card["profile_available"] is False
    assert card["contact_authorized"] is False
    assert not {"contacts", "bio", "evidence", "skills", "fsp", "title"} & card.keys()


def test_24_cards_and_repeated_access_use_three_selects(projection_database):
    with projection_database() as db:
        candidates, company = population(db), db.get(Company, "company-A")
        with select_counter(db.bind) as statements:
            prime_projection_access(db, candidates, company)
            cards = [candidate_projection(db, candidate, company) for candidate in candidates]
            # Repeated checks are real call sites, not a one-use cache shortcut.
            assert all(candidate_accessible(db, row, company) for row in candidates)
            assert [has_grant(db, row, company) for row in candidates] == [i % 3 == 0 for i in range(24)]
        assert len(statements) == 3, statements
        assert len(cards) == 24
        for index, card in enumerate(cards):
            assert card["contact_authorized"] is (index % 3 == 0)
            if index % 3 == 0:
                assert card["name"] == f"Private name {index}"
                assert card["contacts"]["email"] == f"person{index}@example.invalid"
            else:
                assert card["name"] == f"Alias {index}"
                assert card["bio"] == "" and "contacts" not in card


def test_bulk_latest_consent_verification_and_block_are_fail_closed(projection_database):
    with projection_database() as db:
        db.add(Consent(account_id="a00", purpose="processing", granted=False))
        db.get(Account, "a03").email_verified = False
        db.add(CompanyBlock(candidate_id="c06", company_id="company-A"))
        db.query(Consent).filter(Consent.account_id == "a09").delete()
        db.commit()
    with projection_database() as db:
        candidates, company = population(db), db.get(Company, "company-A")
        with select_counter(db.bind) as statements:
            prime_projection_access(db, candidates, company)
            cards = {row.id: candidate_projection(db, row, company) for row in candidates}
        assert len(statements) == 3
        for candidate_id in ("c00", "c03", "c06", "c09"):
            assert_unavailable(cards[candidate_id])
        assert cards["c12"]["contact_authorized"]


def test_company_scope_unknown_population_and_identity_mismatch(projection_database):
    with projection_database() as db:
        candidates = population(db)
        first, second = db.get(Company, "company-A"), db.get(Company, "company-B")
        prime_projection_access(db, candidates[:1], first)
        assert has_grant(db, candidates[0], first)
        # A published card omitted from this exact bulk population is not admitted.
        assert_unavailable(candidate_projection(db, candidates[1], first))
        forged = Candidate(id=candidates[0].id, account_id=candidates[1].account_id, alias="forged")
        assert not candidate_accessible(db, forged, first)
        assert not has_grant(db, forged, first)
        # Another company must query its own permissions and never inherit A's grant.
        second_card = candidate_projection(db, candidates[0], second)
        assert second_card["contact_authorized"] is False and "contacts" not in second_card
        assert candidate_accessible(db, candidates[1], second)
        # Explicit re-prime replaces the scope rather than accumulating authority.
        prime_projection_access(db, candidates[:1], second)
        assert not has_grant(db, candidates[0], second)
        assert has_grant(db, candidates[0], first)


@pytest.mark.parametrize("change", ["grant", "processing", "block"])
def test_next_request_observes_revocation_without_shared_cache(projection_database, change):
    with projection_database() as db:
        candidate, company = db.get(Candidate, "c00"), db.get(Company, "company-A")
        prime_projection_access(db, [candidate], company)
        assert candidate_projection(db, candidate, company)["contact_authorized"]
    with projection_database() as db:
        if change == "grant":
            db.scalar(select(ContactGrant).where(ContactGrant.candidate_id == "c00")).revoked_at = utcnow()
        elif change == "processing":
            db.add(Consent(account_id="a00", purpose="processing", granted=False))
        else:
            db.add(CompanyBlock(candidate_id="c00", company_id="company-A"))
        db.commit()
    with projection_database() as db:
        assert "projection_access" not in db.info
        candidate, company = db.get(Candidate, "c00"), db.get(Company, "company-A")
        prime_projection_access(db, [candidate], company)
        card = candidate_projection(db, candidate, company)
        if change == "grant":
            assert card["contact_authorized"] is False and "contacts" not in card
        else:
            assert_unavailable(card)


@pytest.mark.parametrize("flush_first", [False, True])
def test_permission_write_invalidates_primed_access_in_same_session(projection_database, flush_first):
    with projection_database() as db:
        candidate, company = db.get(Candidate, "c00"), db.get(Company, "company-A")
        grant = db.scalar(select(ContactGrant).where(ContactGrant.candidate_id == candidate.id))
        prime_projection_access(db, [candidate], company)
        assert candidate_projection(db, candidate, company)["contact_authorized"]
        grant.revoked_at = utcnow()
        if flush_first:
            db.flush()
        card = candidate_projection(db, candidate, company)
        assert card["contact_authorized"] is False and "contacts" not in card
        db.add(Consent(account_id=candidate.account_id, purpose="processing", granted=False))
        if flush_first:
            db.flush()
        assert_unavailable(candidate_projection(db, candidate, company))


def test_transaction_boundary_discards_snapshot_in_reused_session(projection_database):
    with projection_database() as db:
        candidate, company = db.get(Candidate, "c00"), db.get(Company, "company-A")
        prime_projection_access(db, [candidate], company)
        assert candidate_projection(db, candidate, company)["contact_authorized"]
        db.commit()
        with projection_database() as writer:
            writer.add(CompanyBlock(candidate_id=candidate.id, company_id=company.id))
            writer.commit()
        # Even when an operator reuses a Session after commit, no old allow survives.
        assert_unavailable(candidate_projection(db, candidate, company))


def test_single_candidate_without_priming_uses_fresh_permissions(projection_database):
    with projection_database() as db:
        candidate, company = db.get(Candidate, "c00"), db.get(Company, "company-A")
        assert candidate_projection(db, candidate, company)["contact_authorized"]
        grant = db.scalar(select(ContactGrant).where(ContactGrant.candidate_id == candidate.id))
        grant.revoked_at = utcnow()
        db.flush()
        card = candidate_projection(db, candidate, company)
        assert not card["contact_authorized"] and "contacts" not in card

"""Actual-route regressions for historical context privacy and company lifecycle."""
from copy import deepcopy
from dataclasses import replace
import json

import pytest
from sqlalchemy import func, select

from app.models import Account, Application, AuditEvent, Candidate, ChallengeSubmission, ContactGrant, Delivery, Invitation, Notification, Outbox
from test_domain_api import database, confirm_fixture, invite, logged, need_body


def test_raw_non_ascii_csrf_header_is_rejected_without_logout_or_session_change(database):
    from app.models import BrowserSession
    client = logged()
    before = client.get('/api/v1/auth/me').json()
    with database() as db:
        session_ids = list(db.scalars(select(BrowserSession.id)).all())
    response = client.post('/api/v1/auth/logout', headers=[(b'x-csrf-token', b'\xff')])
    assert response.status_code == 403 and response.json()['code'] == 'CSRF_REJECTED'
    current = client.get('/api/v1/auth/me')
    assert current.status_code == 200 and current.json()['id'] == before['id']
    assert current.json()['csrf_token'] == before['csrf_token']
    with database() as db:
        assert list(db.scalars(select(BrowserSession.id)).all()) == session_ids
    # A valid token retains the intended logout behavior after the rejected request.
    assert client.post('/api/v1/auth/logout').status_code == 200
    assert client.get('/api/v1/auth/me').status_code == 401


def hiring_context(database):
    confirm_fixture(database)
    candidate, employer = logged(), logged('employer@vector.local')
    vacancy = employer.post('/api/v1/vacancies', json=need_body()).json()
    invitation = invite(employer).json()
    accepted = candidate.post(f"/api/v1/invitations/{invitation['id']}/accept").json()
    challenge = employer.post('/api/v1/challenges', json={'title':'Проверка API',
        'description':'Опишите обработку повторного запроса API.', 'specialization':'backend', 'skill':'API',
        'public_task':{'type':'text','prompt':'Как обрабатывать повтор?'}}).json()
    marker = 'SYNTHETIC-PRIVATE-CONTEXT@example.invalid'
    submission = candidate.post(f"/api/v1/challenges/{challenge['id']}/submit", json={'answer':marker}).json()
    application = candidate.post(f"/api/v1/vacancies/{vacancy['id']}/apply",
        json={'message':marker, 'consent_contacts':True}).json()
    assert candidate.post(f"/api/v1/invitations/{invitation['id']}/messages", json={'text':marker}).status_code == 201
    assert employer.post(f"/api/v1/invitations/{invitation['id']}/messages", json={'text':'Employer own message'}).status_code == 201
    return candidate, employer, challenge, submission, application, invitation, accepted, marker


@pytest.mark.parametrize('restriction,reason,status', [('processing','processing_withdrawn',409), ('block','company_blocked',403)])
def test_historical_private_context_redaction_and_review_denial_preserve_evidence(database, restriction, reason, status):
    candidate, employer, challenge, submission, application, invitation, accepted, marker = hiring_context(database)
    review_path = f"/api/v1/challenges/{challenge['id']}/submissions/{submission['id']}/review"
    assert employer.post(review_path, json={'score':80, 'feedback':'Субъективный отзыв компании'}).status_code == 200
    with database() as db:
        original_result = deepcopy(db.get(ChallengeSubmission, submission['id']).result)
        original_categories = deepcopy(db.get(Candidate, 'candidate-1').confirmed_categories)
    if restriction == 'processing':
        assert candidate.post('/api/v1/candidate/consents', json={'purpose':'processing','granted':False}).status_code == 200
    else:
        assert candidate.post('/api/v1/candidate/companies/company-3/block').status_code == 200
    history = employer.get(f"/api/v1/challenges/{challenge['id']}/submissions")
    assert history.status_code == 200 and marker not in history.text
    record = history.json()['items'][0]
    assert record['id'] == submission['id'] and record['created_at'] == submission['created_at']
    assert record['answer'] is None and record['result'] == {'status':'content_unavailable','content_redacted':True}
    assert record['content_redacted'] and not record['private_content_available'] and record['privacy_reason'] == reason
    applications = employer.get('/api/v1/applications')
    assert applications.status_code == 200 and marker not in applications.text
    record = applications.json()['items'][0]
    assert record['id'] == application['id'] and record['status'] == application['status'] and record['message'] == ''
    assert record['content_redacted'] and record['privacy_reason'] == reason
    discussion = employer.get(f"/api/v1/invitations/{invitation['id']}")
    assert discussion.status_code == 200 and marker not in discussion.text
    record = discussion.json()
    assert record['status'] == 'accepted' and record['privacy_reason'] == reason and record['content_redacted']
    assert any(row['author_role'] == 'candidate' and row['text'] == '' and row['content_redacted'] for row in record['messages'])
    assert any(row['text'] == 'Employer own message' and not row['content_redacted'] for row in record['messages'])
    denied = employer.post(review_path, json={'score':100,'feedback':'Новая оценка запрещена'})
    assert denied.status_code == status and denied.json()['code'] == ('CANDIDATE_UNAVAILABLE' if restriction == 'processing' else 'COMPANY_BLOCKED')
    with database() as db:
        row = db.get(ChallengeSubmission, submission['id'])
        assert row.answer == {'value':marker} and row.result == original_result
        assert db.get(Application, application['id']).message == marker
        assert db.get(Candidate, 'candidate-1').confirmed_categories == original_categories
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == 'challenge.company_reviewed')) == 1
        assert db.scalar(select(func.count()).select_from(Notification).where(Notification.kind == 'challenge.reviewed')) == 1


def test_contact_revocation_alone_keeps_voluntary_context_and_owner_history(database):
    candidate, employer, challenge, submission, application, invitation, accepted, marker = hiring_context(database)
    assert candidate.post(f"/api/v1/candidate/contact-grants/{accepted['contact_grant_id']}/revoke").status_code == 200
    discussion = employer.get(f"/api/v1/invitations/{invitation['id']}").json()
    assert not discussion['contacts_open'] and not discussion['candidate']['contact_authorized']
    assert discussion['private_content_available'] and any(row['text'] == marker for row in discussion['messages'])
    assert employer.get('/api/v1/applications').json()['items'][0]['message'] == marker
    assert employer.get(f"/api/v1/challenges/{challenge['id']}/submissions").json()['items'][0]['answer'] == {'value':marker}
    assert candidate.post('/api/v1/candidate/companies/company-3/block').status_code == 200
    own = candidate.get('/api/v1/applications').json()['items'][0]
    assert own['message'] == marker and own['private_content_available'] and not own['content_redacted']
    own_discussion = candidate.get(f"/api/v1/invitations/{invitation['id']}").json()
    assert any(row['text'] == marker for row in own_discussion['messages'])


def test_inactive_employer_cannot_receive_new_hiring_actions_and_regrant_restores_availability(database):
    confirm_fixture(database)
    candidate, employer = logged(), logged('employer@vector.local')
    vacancy = employer.post('/api/v1/vacancies', json=need_body()).json()
    invitation = invite(employer).json()
    assert employer.post('/api/v1/auth/consents', json={'consent_processing':False}).status_code == 200
    assert employer.get('/api/v1/employer/company').status_code == 403
    assert candidate.get('/api/v1/vacancies').json()['items'] == []
    assert candidate.get(f"/api/v1/vacancies/{vacancy['id']}").status_code == 404
    applied = candidate.post(f"/api/v1/vacancies/{vacancy['id']}/apply", json={'consent_contacts':True})
    accepted = candidate.post(f"/api/v1/invitations/{invitation['id']}/accept")
    assert applied.status_code == accepted.status_code == 409
    assert applied.json()['code'] == accepted.json()['code'] == 'COMPANY_UNAVAILABLE'
    with database() as db:
        assert db.get(Invitation, invitation['id']).status == 'pending'
        assert db.scalar(select(func.count()).select_from(ContactGrant)) == 0
        assert db.scalar(select(func.count()).select_from(Application)) == 0
        assert not db.scalar(select(Outbox).where(Outbox.kind == 'ats.invitation_accepted'))
    assert employer.post('/api/v1/auth/consents', json={'consent_processing':True}).status_code == 200
    assert candidate.get(f"/api/v1/vacancies/{vacancy['id']}").status_code == 200
    assert candidate.post(f"/api/v1/vacancies/{vacancy['id']}/apply", json={'consent_contacts':True}).status_code == 201
    assert candidate.post(f"/api/v1/invitations/{invitation['id']}/accept").status_code == 200


def test_unverified_company_owner_does_not_pass_hiring_admission(database):
    confirm_fixture(database)
    candidate, employer = logged(), logged('employer@vector.local')
    vacancy = employer.post('/api/v1/vacancies', json=need_body()).json()
    invitation = invite(employer).json()
    with database() as db:
        db.get(Account, 'account-3').email_verified = False
        db.commit()
    assert candidate.get('/api/v1/vacancies').json()['items'] == []
    assert candidate.post(f"/api/v1/vacancies/{vacancy['id']}/apply", json={'consent_contacts':True}).status_code == 409
    assert candidate.post(f"/api/v1/invitations/{invitation['id']}/accept").status_code == 409


def test_company_processing_withdrawal_hides_current_practice_and_prevents_new_submission(database):
    from app.models import Challenge
    candidate, employer = logged(), logged('employer@vector.local')
    challenge = employer.post('/api/v1/challenges', json={'title':'Компания API',
        'description':'Опишите обработку повторного запроса API.', 'specialization':'backend', 'skill':'API',
        'public_task':{'type':'text','prompt':'Как обрабатывать повтор?'}}).json()
    assert candidate.get(f"/api/v1/challenges/{challenge['id']}").status_code == 200
    employer.post('/api/v1/auth/consents', json={'consent_processing':False})
    assert candidate.get('/api/v1/challenges').json()['items'] == []
    assert candidate.get(f"/api/v1/challenges/{challenge['id']}").status_code == 404
    rejected = candidate.post(f"/api/v1/challenges/{challenge['id']}/submit", json={'answer':'A new synthetic answer'})
    assert rejected.status_code == 409 and rejected.json()['code'] == 'COMPANY_UNAVAILABLE'
    with database() as db:
        assert db.get(Challenge, challenge['id']).published
        assert db.scalar(select(func.count()).select_from(ChallengeSubmission)) == 0
    employer.post('/api/v1/auth/consents', json={'consent_processing':True})
    assert candidate.get(f"/api/v1/challenges/{challenge['id']}").status_code == 200
    assert candidate.post(f"/api/v1/challenges/{challenge['id']}/submit", json={'answer':'A synthetic answer'}).status_code == 201


def test_inactive_company_cannot_create_new_need_practice_from_invitation_or_vacancy(database):
    from app.models import AssessmentAttempt
    confirm_fixture(database)
    candidate, employer = logged(), logged('employer@vector.local')
    vacancy = employer.post('/api/v1/vacancies', json=need_body()).json()
    need = employer.post('/api/v1/employer/needs', json=need_body()).json()
    invitation = invite(employer, need_id=need['id']).json()
    employer.post('/api/v1/auth/consents', json={'consent_processing':False})
    for context in [{'invitation_id':invitation['id']}, {'vacancy_id':vacancy['id']}]:
        rejected = candidate.post('/api/v1/assessments/need-start', json=context)
        assert rejected.status_code == 409 and rejected.json()['code'] == 'COMPANY_UNAVAILABLE'
    with database() as db:
        assert db.scalar(select(func.count()).select_from(AssessmentAttempt)) == 0
        assert db.get(Invitation, invitation['id']).status == 'pending'
        assert db.get(Candidate, 'candidate-1').confirmed_grade == 'junior'
    employer.post('/api/v1/auth/consents', json={'consent_processing':True})
    assert candidate.post('/api/v1/assessments/need-start', json={'vacancy_id':vacancy['id']}).status_code == 201


def test_inactive_company_stops_new_invitation_messages_without_erasing_history(database):
    from app.models import InvitationMessage
    confirm_fixture(database)
    candidate, employer = logged(), logged('employer@vector.local')
    invitation = invite(employer).json()
    assert candidate.post(f"/api/v1/invitations/{invitation['id']}/accept").status_code == 200
    path = f"/api/v1/invitations/{invitation['id']}/messages"
    assert candidate.post(path, json={'text':'Historical synthetic context'}).status_code == 201
    employer.post('/api/v1/auth/consents', json={'consent_processing':False})
    rejected = candidate.post(path, json={'text':'New context must not be delivered'})
    assert rejected.status_code == 409 and rejected.json()['code'] == 'COMPANY_UNAVAILABLE'
    assert any(row['text'] == 'Historical synthetic context' for row in candidate.get(f"/api/v1/invitations/{invitation['id']}").json()['messages'])
    with database() as db:
        assert db.scalar(select(func.count()).select_from(InvitationMessage)) == 1
        assert db.scalar(select(func.count()).select_from(Notification).where(Notification.kind == 'invitation.message')) == 1
    employer.post('/api/v1/auth/consents', json={'consent_processing':True})
    assert candidate.post(path, json={'text':'New context after explicit regrant'}).status_code == 201


@pytest.mark.parametrize('restriction,status,code', [('processing',409,'CANDIDATE_UNAVAILABLE'), ('block',403,'COMPANY_BLOCKED')])
def test_private_candidate_scope_stops_application_status_actions_and_notifications(database, restriction, status, code):
    candidate, employer, challenge, submission, application, invitation, accepted, marker = hiring_context(database)
    if restriction == 'processing':
        candidate.post('/api/v1/candidate/consents', json={'purpose':'processing','granted':False})
    else:
        candidate.post('/api/v1/candidate/companies/company-3/block')
    rejected = employer.patch(f"/api/v1/applications/{application['id']}", json={'status':'offer'})
    assert rejected.status_code == status and rejected.json()['code'] == code
    with database() as db:
        row = db.get(Application, application['id'])
        assert row.status == 'new' and row.message == marker
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == 'application.updated')) == 0
        assert db.scalar(select(func.count()).select_from(Notification).where(Notification.kind == 'application.updated')) == 0


@pytest.mark.parametrize('value', [float('nan'), float('inf'), '\ud800'], ids=['NaN','Infinity','invalid-Unicode'])
def test_company_practice_rejects_unpersistable_json_and_keeps_history_readable(database, value):
    candidate, employer = logged(), logged('employer@vector.local')
    challenge = employer.post('/api/v1/challenges', json={'title':'Компания API',
        'description':'Опишите обработку повторного запроса API.', 'specialization':'backend', 'skill':'API',
        'public_task':{'type':'text','prompt':'Как обрабатывать повтор?'}}).json()
    path = f"/api/v1/challenges/{challenge['id']}"
    rejected = candidate.post(path + '/submit', content=json.dumps({'answer':{'metric':value}}, allow_nan=True),
        headers={'Content-Type':'application/json'})
    assert rejected.status_code == 422 and rejected.json()['code'] == 'ANSWER_JSON_INVALID'
    assert employer.get(path + '/submissions').json()['items'] == []
    with database() as db:
        assert db.scalar(select(func.count()).select_from(ChallengeSubmission)) == 0
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == 'challenge.submitted')) == 0
        assert db.get(Candidate, 'candidate-1').evidence == []
        assert db.get(Candidate, 'candidate-1').confirmed_grade is None
    # Text submitted for human review is not parsed as JSON by this guard.
    repaired = candidate.post(path + '/submit', json={'answer':'{ unfinished explanation'})
    assert repaired.status_code == 201
    history = employer.get(path + '/submissions')
    assert history.status_code == 200 and history.json()['items'][0]['answer'] == {'value':'{ unfinished explanation'}


@pytest.mark.parametrize('restriction,expected', [('company','cancelled_company_unavailable'),
    ('processing','cancelled_permission_revoked'), ('block','cancelled_permission_revoked')])
def test_ats_dispatch_rechecks_current_candidate_and_company_before_transport(database, monkeypatch, restriction, expected):
    import app.worker as worker
    confirm_fixture(database)
    candidate, employer = logged(), logged('employer@vector.local')
    invitation = invite(employer).json()
    assert candidate.post(f"/api/v1/invitations/{invitation['id']}/accept").status_code == 200
    if restriction == 'company':
        employer.post('/api/v1/auth/consents', json={'consent_processing':False})
    elif restriction == 'processing':
        candidate.post('/api/v1/candidate/consents', json={'purpose':'processing','granted':False})
    else:
        candidate.post('/api/v1/candidate/companies/company-3/block')
    monkeypatch.setattr(worker,'settings',replace(worker.settings,ats_webhook_url='http://127.0.0.1:8090/events',ats_webhook_secret='synthetic-key'))
    def no_transport(*args, **kwargs):
        raise AssertionError('Revoked or inactive scope must never reach the transport')
    monkeypatch.setattr(worker.httpx,'post',no_transport)
    worker.consume_once()
    with database() as db:
        event = db.scalar(select(Outbox).where(Outbox.kind == 'ats.invitation_accepted'))
        assert event.status == expected and event.completed_at and event.attempts == 1
        assert db.scalar(select(func.count()).select_from(Delivery)) == 0

"""Real persisted-route checks for review receipts, lifecycle and no grade preview."""
import json
from copy import deepcopy
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.models import AssessmentAttempt, AuditEvent, Candidate, ContactGrant, Notification, utcnow
from test_domain_api import database, confirm_fixture, create_attempt, logged, need_body, reference_answers


def receipt(client, attempt_id, answers):
    response = client.post(f'/api/v1/assessments/{attempt_id}/review', json={'answers':answers})
    assert response.status_code == 200, response.text
    return response.json()


def assert_open_unchanged(sessions, attempt_id, saved=None):
    with sessions() as db:
        row = db.get(AssessmentAttempt, attempt_id)
        assert row.status == 'in_progress' and row.result is None and row.finished_at is None
        assert row.answers == (saved or {})
        assert db.get(Candidate, row.candidate_id).confirmed_grade is None
        assert db.scalar(select(func.count()).select_from(Notification).where(Notification.kind == 'assessment.completed')) == 0


def test_review_is_nonmutating_public_and_receipt_submit_idempotent(database, monkeypatch):
    import app.engines.assessment as engine
    client = logged()
    attempt = create_attempt(client)
    answers = reference_answers(database, attempt['id'])
    grade = engine.grade_assessment
    calls = []
    def track_grade(*args, **kwargs):
        calls.append(True)
        return grade(*args, **kwargs)
    monkeypatch.setattr(engine, 'grade_assessment', track_grade)
    reviewed = receipt(client, attempt['id'], answers)
    assert reviewed['structural_ready'] and reviewed['answered'] == reviewed['total'] == len(attempt['items'])
    assert reviewed['issues'] == [] and len(reviewed['review_token']) == 64
    assert len(reviewed['public_form_sha256']) == len(reviewed['prospective_answers_sha256']) == 64
    assert not {'answers','score','passed','confirmed_grade','private_payload','items'} & set(reviewed)
    assert '_oracle' not in json.dumps(reviewed) and calls == []
    assert_open_unchanged(database, attempt['id'])
    finished = client.post(f"/api/v1/assessments/{attempt['id']}/submit", json={
        'answers':answers, 'review_token':reviewed['review_token']})
    assert finished.status_code == 200 and finished.json()['result']['score'] == 100
    assert finished.json()['result']['certifies_global_category']
    repeated = client.post(f"/api/v1/assessments/{attempt['id']}/submit", json={'answers':{'unknown':'invalid'},'review_token':'stale'})
    assert repeated.status_code == 200 and repeated.json()['result'] == finished.json()['result'] and calls == [True]
    assert client.post(f"/api/v1/assessments/{attempt['id']}/review", json={'answers':answers}).status_code == 409
    with database() as db:
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == 'assessment.completed')) == 1


@pytest.mark.parametrize('bad_kind', ['json-syntax','choice','nonfinite','unknown','sql-limit'])
def test_bad_representation_never_consumes_or_grades_attempt_and_can_be_repaired(database, monkeypatch, bad_kind):
    import app.engines.assessment as engine
    client = logged()
    attempt = create_attempt(client)
    good = reference_answers(database, attempt['id'])
    answers = deepcopy(good)
    if bad_kind == 'json-syntax':
        item = next(item for item in attempt['items'] if item['type'] == 'json')
        answers[item['id']] = '{ malformed'
    elif bad_kind == 'choice':
        item = next(item for item in attempt['items'] if item['type'] == 'single_choice')
        answers[item['id']] = 'not-an-option'
    elif bad_kind == 'nonfinite':
        item = next(item for item in attempt['items'] if item['type'] == 'json')
        answers[item['id']] = float('nan')
    elif bad_kind == 'unknown':
        answers['unknown-private-key-should-not-echo'] = 'untrusted'
    else:
        item = next(item for item in attempt['items'] if item['type'] == 'sql')
        answers[item['id']] = 'SELECT ' + 'x' * 12001
    # Real HTTP JSON with a non-finite extension verifies the server boundary,
    # while allowing the helper to return only canonical, safe JSON output.
    request = {'content':json.dumps({'answers':answers}, allow_nan=True), 'headers':{'Content-Type':'application/json'}}
    reviewed = client.post(f"/api/v1/assessments/{attempt['id']}/review", **request)
    assert reviewed.status_code == 200 and not reviewed.json()['structural_ready']
    assert any(issue['kind'] in {'format','limit'} for issue in reviewed.json()['issues'])
    assert 'unknown-private-key-should-not-echo' not in reviewed.text
    calls = []
    original = engine.grade_assessment
    def forbidden_grade(*args, **kwargs):
        calls.append(True)
        raise AssertionError('Invalid representation must not reach grading')
    monkeypatch.setattr(engine, 'grade_assessment', forbidden_grade)
    rejected = client.post(f"/api/v1/assessments/{attempt['id']}/submit", **request)
    assert rejected.status_code == 422 and rejected.json()['code'] == 'ASSESSMENT_ANSWER_INVALID' and calls == []
    assert_open_unchanged(database, attempt['id'])
    monkeypatch.setattr(engine, 'grade_assessment', original)
    reviewed = receipt(client, attempt['id'], good)
    completed = client.post(f"/api/v1/assessments/{attempt['id']}/submit", json={'answers':good, 'review_token':reviewed['review_token']})
    assert completed.status_code == 200 and completed.json()['result']['score'] == 100


def test_review_missing_requires_explicit_receipt_opt_in_and_preserves_legacy_failure(database):
    client = logged()
    attempt = create_attempt(client)
    reviewed = receipt(client, attempt['id'], {})
    assert reviewed['answered'] == 0 and not reviewed['structural_ready']
    assert all(issue['kind'] == 'missing' for issue in reviewed['issues'])
    path = f"/api/v1/assessments/{attempt['id']}/submit"
    rejected = client.post(path, json={'answers':{},'review_token':reviewed['review_token']})
    assert rejected.status_code == 422 and rejected.json()['code'] == 'ASSESSMENT_INCOMPLETE'
    assert_open_unchanged(database, attempt['id'])
    completed = client.post(path, json={'answers':{},'review_token':reviewed['review_token'],'allow_incomplete':True})
    assert completed.status_code == 200 and not completed.json()['result']['passed']
    assert not completed.json()['result']['category_changed']
    # Older clients retain the explicitly supported missing-answer grading path.
    other = logged('other@vector.local')
    old_attempt = create_attempt(other)
    old = other.post(f"/api/v1/assessments/{old_attempt['id']}/submit", json={'answers':{}})
    assert old.status_code == 200 and not old.json()['result']['passed']


def test_receipt_tracks_final_snapshot_and_public_form_without_false_autosave_stale(database):
    client = logged()
    attempt = create_attempt(client)
    answers = reference_answers(database, attempt['id'])
    reviewed = receipt(client, attempt['id'], answers)
    path = f"/api/v1/assessments/{attempt['id']}"
    changed = deepcopy(answers)
    item = next(item for item in attempt['items'] if item['type'] == 'number')
    changed[item['id']] = float(answers[item['id']]) + 1
    rejected = client.post(path + '/submit', json={'answers':changed,'review_token':reviewed['review_token']})
    assert rejected.status_code == 409 and rejected.json()['code'] == 'REVIEW_STALE'
    assert_open_unchanged(database, attempt['id'])
    # Autosaving the same final snapshot changes diagnostic saved SHA only.
    assert client.put(path + '/answers', json={'answers':answers}).status_code == 200
    saved_review = receipt(client, attempt['id'], {})
    assert saved_review['saved_answers_sha256'] != reviewed['saved_answers_sha256']
    assert saved_review['review_token'] == reviewed['review_token']
    assert client.put(path + '/answers', json={'answers':{item['id']:changed[item['id']]}}).status_code == 200
    rejected = client.post(path + '/submit', json={'answers':{},'review_token':reviewed['review_token']})
    assert rejected.status_code == 409 and rejected.json()['code'] == 'REVIEW_STALE'
    # A full reviewed draft overrides changed saved values; no cross-tab CAS is claimed.
    assert receipt(client, attempt['id'], answers)['review_token'] == reviewed['review_token']
    with database() as db:
        row = db.get(AssessmentAttempt, attempt['id'])
        form = deepcopy(row.private_form)
        form['items'][0]['prompt'] += ' Дополнительное публичное условие.'
        row.private_form = form
        db.commit()
    changed_form = client.post(path + '/submit', json={'answers':answers,'review_token':reviewed['review_token']})
    assert changed_form.status_code == 409 and changed_form.json()['code'] == 'REVIEW_STALE'
    assert receipt(client, attempt['id'], answers)['public_form_sha256'] != reviewed['public_form_sha256']
    updated = receipt(client, attempt['id'], answers)
    completed = client.post(path + '/submit', json={'answers':answers,'review_token':updated['review_token']})
    assert completed.status_code == 200 and completed.json()['result']['passed']


@pytest.mark.parametrize('token,status', [('я' * 64,409), ('\ud800',422)], ids=['non-ASCII','lone-surrogate'])
def test_review_owner_deadline_and_non_ascii_token_fail_closed_without_mutations(database, token, status):
    client = logged()
    attempt = create_attempt(client)
    path = f"/api/v1/assessments/{attempt['id']}"
    assert logged('other@vector.local').post(path + '/review', json={'answers':{}}).status_code == 404
    unicode_token = client.post(path + '/submit', content=json.dumps({'answers':{},'review_token':token}),
        headers={'Content-Type':'application/json'})
    assert unicode_token.status_code == status
    if status == 409:
        assert unicode_token.json()['code'] == 'REVIEW_STALE'
    else:
        # Pydantic's typed string rejects malformed Unicode before the handler.
        assert unicode_token.json()['status'] == 422 and unicode_token.json()['code'] == 'VALIDATION_ERROR'
    assert_open_unchanged(database, attempt['id'])
    with database() as db:
        db.get(AssessmentAttempt, attempt['id']).expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    assert client.post(path + '/review', json={'answers':{}}).json()['code'] == 'ATTEMPT_CLOSED'
    with database() as db:
        assert db.get(AssessmentAttempt, attempt['id']).status == 'in_progress'
        assert db.get(AssessmentAttempt, attempt['id']).answers == {}


@pytest.mark.parametrize('bad_value', [float('nan'), float('inf'), '\ud800'], ids=['NaN','Infinity','invalid-Unicode'])
def test_autosave_rejects_unpersistable_native_json_without_blocking_incomplete_strings(database, bad_value):
    client = logged()
    attempt = create_attempt(client)
    item = next(item for item in attempt['items'] if item['type'] == 'json')
    path = f"/api/v1/assessments/{attempt['id']}/answers"
    rejected = client.put(path, content=json.dumps({'answers':{item['id']:bad_value}}, allow_nan=True),
        headers={'Content-Type':'application/json'})
    assert rejected.status_code == 422 and rejected.json()['code'] == 'ANSWER_JSON_INVALID'
    assert_open_unchanged(database, attempt['id'])
    saved = client.put(path, json={'answers':{item['id']:'{ incomplete JSON'}})
    assert saved.status_code == 200 and saved.json()['answers'] == {item['id']:'{ incomplete JSON'}
    reviewed = receipt(client, attempt['id'], {})
    assert any(issue['kind'] == 'format' and issue['item_id'] == item['id'] for issue in reviewed['issues'])


def test_autosave_bounds_prospective_merge_and_native_structure(database):
    client = logged()
    attempt = create_attempt(client)
    ids = [item['id'] for item in attempt['items']]
    path = f"/api/v1/assessments/{attempt['id']}/answers"
    first = {ids[0]:'x' * 60000}
    assert client.put(path, json={'answers':first}).status_code == 200
    rejected = client.put(path, json={'answers':{ids[1]:'x' * 60000}})
    assert rejected.status_code in {413,422}
    nested = []
    for _ in range(35):
        nested = [nested]
    complex_draft = client.put(path, json={'answers':{ids[1]:nested}})
    assert complex_draft.status_code == 422 and complex_draft.json()['code'] == 'ANSWER_JSON_INVALID'
    assert_open_unchanged(database, attempt['id'], first)


@pytest.mark.parametrize('scope', ['demo','employer_need_practice'])
def test_receipt_does_not_upgrade_demo_or_need_practice_into_formal_evidence(database, scope):
    client = logged()
    if scope == 'demo':
        client.post('/api/v1/candidate/survey', json={'industry':'ИТ','specialization':'backend','grade':'junior','stack':['SQL']})
        attempt = client.post('/api/v1/assessments/start', json={'specialization':'backend','grade':'junior','stack':['SQL'],'demo':True}).json()
    else:
        confirm_fixture(database)
        vacancy = logged('employer@vector.local').post('/api/v1/vacancies', json=need_body()).json()
        attempt = client.post('/api/v1/assessments/need-start', json={'vacancy_id':vacancy['id']}).json()
    with database() as db:
        before = deepcopy(db.get(Candidate, 'candidate-1').confirmed_categories)
        evidence = deepcopy(db.get(Candidate, 'candidate-1').evidence)
    answers = reference_answers(database, attempt['id'])
    reviewed = receipt(client, attempt['id'], answers)
    completed = client.post(f"/api/v1/assessments/{attempt['id']}/submit", json={'answers':answers,'review_token':reviewed['review_token']})
    assert completed.status_code == 200 and completed.json()['result']['passed']
    assert not completed.json()['result']['certifies_global_category'] and not completed.json()['result']['category_changed']
    with database() as db:
        candidate = db.get(Candidate, 'candidate-1')
        assert candidate.confirmed_categories == before
        assert [item for item in candidate.evidence if item['source'] == 'ASSESSMENT_VERIFIED'] == [item for item in evidence if item['source'] == 'ASSESSMENT_VERIFIED']
        assert db.scalar(select(func.count()).select_from(ContactGrant)) == 0

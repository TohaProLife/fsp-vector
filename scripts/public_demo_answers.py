"""Prepare transparent automated control answers for a synthetic local actor.

Reads only the actor's ordinary public attempt DTO. Never writes an answer,
submits an attempt, changes a score, or reads a private grading payload. The
reference solver is authored evaluation code, not a human validity experiment.
Answers are entered and submitted through the actual browser separately.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluation.reference_solvers import reference_answer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--email', required=True)
    parser.add_argument('--attempt', required=True)
    args = parser.parse_args()
    if not args.email.endswith('@vector.local'):
        raise RuntimeError('Only explicitly synthetic local identities are allowed')
    base = 'http://127.0.0.1:8000'
    with httpx.Client(timeout=15, trust_env=False) as client:
        health = client.get(base + '/health')
        health.raise_for_status()
        if health.json().get('environment') != 'local_demo':
            raise RuntimeError('Refusing a non-demo service')
        identity = client.post(base + '/api/v1/auth/login',
            json={'email':args.email, 'password':'VectorDemo2026!'},
            headers={'Origin':'http://localhost:3000'})
        identity.raise_for_status()
        response = client.get(base + '/api/v1/assessments/' + args.attempt)
        response.raise_for_status()
        attempt = response.json()
    if attempt['status'] != 'in_progress':
        raise RuntimeError('The ordinary UI must start a fresh attempt first')
    answers = []
    for item in attempt['items']:
        answer = reference_answer(item)
        label = next((option['label'] for option in item.get('options', [])
                      if option['id'] == answer), None)
        answers.append({'id':item['id'], 'title':item['title'], 'type':item['type'],
                        'answer':answer, 'option_label':label})
    target = ROOT / 'output/final-2026-10-11/control-answers.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    report = {'kind':'synthetic_automated_control_public_dto', 'created_at':datetime.now(timezone.utc).isoformat(),
              'attempt_id':attempt['id'], 'answers':answers,
              'public_items_sha256':hashlib.sha256(json.dumps(attempt['items'], sort_keys=True,
                                                       ensure_ascii=False).encode()).hexdigest(),
              'method':'Authored reference solver from public task data and reviewed concept facts; no private oracle read.',
              'mutations':'None. Ordinary browser autosave/review/submit is required.',
              'human_validity':'NOT_MEASURED'}
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    print(json.dumps({'prepared_items':len(answers), 'output':str(target),
                      'grades_or_answers_written_to_server':False}))


if __name__ == '__main__':
    main()

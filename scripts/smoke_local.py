"""Real loopback transport/domain smoke, using explicitly synthetic local identities.

Creates one synthetic verified account, need, invitation and revoked grant. Never
targets a production server or an actual person's email. Does not change grades.
"""
from __future__ import annotations
import json
from pathlib import Path
import re
import sys
import time
from urllib.parse import parse_qs, urlparse
from uuid import uuid4
import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8000/api/v1"
PASSWORD = "VectorDemo2026!"


def request(client, method, path, expected=200, **kwargs):
    response = client.request(method, BASE + path, **kwargs)
    if response.status_code != expected:
        try:
            code = response.json().get("code", "unexpected_status")
        except ValueError:
            code = "non_json_response"
        raise RuntimeError(f"{method} {path.split('?')[0]}: {response.status_code} {code}")
    return response.json()


def login(email):
    client = httpx.Client(timeout=20)
    data = request(client, "POST", "/auth/login", json={"email": email, "password": PASSWORD})
    client.headers.update({"X-CSRF-Token": data["csrf_token"], "Origin": "http://localhost:3000"})
    return client, data


def wait_until(operation, label, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = operation()
        if result:
            return result
        time.sleep(0.5)
    raise RuntimeError(f"Timed out: {label}")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    report = {"kind": "real_loopback_smoke", "identity_data": "synthetic", "checks": []}
    anonymous = httpx.Client(timeout=20)
    health = request(anonymous, "GET", "/health")
    assert health["environment"] == "local_demo", "Refusing production smoke mutations"
    assert health["database"] == "postgresql"
    email = "smoke-" + uuid4().hex[:12] + "@vector.local"
    request(anonymous, "POST", "/auth/register", expected=201, json={"name": "Синтетический аудит доставки",
        "email": email, "password": PASSWORD, "role": "candidate", "consent_processing": True})

    def delivered_message():
        messages = httpx.get("http://127.0.0.1:8025/api/v1/messages", timeout=3).json().get("messages", [])
        found = next((row for row in messages if any(to.get("Address") == email for to in row.get("To", []))), None)
        return httpx.get("http://127.0.0.1:8025/api/v1/message/" + found["ID"], timeout=3).json() if found else None
    mail = wait_until(delivered_message, "actual SMTP receipt")
    link = re.search(r"http://localhost:3000/verify\?token=[A-Za-z0-9_-]+", mail["Text"]).group()
    token = parse_qs(urlparse(link).query)["token"][0]
    request(anonymous, "GET", "/auth/verify", params={"token": token})
    reused = anonymous.get(BASE + "/auth/verify", params={"token": token})
    assert reused.status_code == 400 and reused.json()["code"] == "VERIFICATION_EXPIRED"
    registered, _ = login(email)
    assert request(registered, "GET", "/auth/me")["email_verified"]
    assert request(registered, "GET", "/candidate/profile")["confirmed_grade"] is None
    report["checks"].append("register → actual SMTP/Mailpit → single-use verification → verified session")

    seed = json.loads((ROOT / "data/demo-seed.json").read_text(encoding="utf-8"))
    identity = next(row for row in seed["candidates"] if row.get("published") and row.get("confirmed_grade"))
    candidate, _ = login(identity["email"])
    employer, _ = login("employer@vector.local")
    other_company, _ = login("employer2@vector.local")
    profile = request(candidate, "GET", "/candidate/profile")
    # Repeated smoke keeps the fixture usable; only this synthetic identity is affected.
    request(candidate, "POST", "/candidate/publication", json={"published": True, "consent_publication": True})
    preferences = profile["preferences"]
    skills = [row["skill"] for row in profile["evidence"] if row.get("skill")][:2]
    need = request(employer, "POST", "/employer/needs", expected=201, json={
        "title": "Синтетический сквозной аудит", "description": "Локальная проверка подбора и scoped contacts.",
        "specialization": profile["specialization"], "grade": profile["confirmed_grade"],
        "skills": skills, "required_skills": [], "salary_from": preferences["salary_from"],
        "salary_to": preferences["salary_to"], "work_format": "any", "employment": "full_time", "team": "Тестовый стенд"})
    match = request(employer, "POST", "/employer/matches", expected=201, json={"need_id": need["id"], "filters": {}})
    assert match["items"] and all("contacts" not in item["candidate"] for item in match["items"])
    cid = profile["id"]
    assert any(item["candidate"]["id"] == cid for item in match["items"])
    request(candidate, "POST", "/candidate/publication", json={"published": False, "consent_publication": False})
    saved = request(employer, "GET", "/employer/matches/" + match["id"])
    assert all(item["candidate"]["id"] != cid for item in saved["items"])
    request(candidate, "POST", "/candidate/publication", json={"published": True, "consent_publication": True})
    report["checks"].append("actual ranking hides contacts; saved run rechecks publication immediately")

    invitation = request(employer, "POST", "/invitations", expected=201, json={"candidate_id": cid,
        "need_id": need["id"], "title": "Локальное тестовое приглашение", "message": "Вымышленное предложение для проверки приложения; не реальный найм.",
        "salary_from": preferences["salary_from"], "salary_to": preferences["salary_to"],
        "work_format": "remote", "employment": "full_time", "contact": "employer@vector.local"})
    iid = invitation["id"]
    assert not request(employer, "GET", "/employer/candidates/" + cid)["contact_authorized"]
    accepted = request(candidate, "POST", "/invitations/" + iid + "/accept")
    grant_id = accepted["contact_grant_id"]
    assert request(employer, "GET", "/employer/candidates/" + cid)["contact_authorized"]
    assert not request(other_company, "GET", "/employer/candidates/" + cid)["contact_authorized"]
    def actual_delivery():
        items = request(employer, "GET", "/employer/ats-deliveries")["items"]
        return next((row for row in items if row["payload"].get("invitation_id") == iid and row["destination"] == "configured_signed_webhook"), None)
    delivery = wait_until(actual_delivery, "actual signed HTTP ATS delivery")
    assert "contacts" not in delivery["payload"] and "email" not in json.dumps(delivery["payload"])
    report["checks"].append("invite → accept → scoped grant → actual signed HTTP ATS receipt; another company stays locked")
    request(candidate, "POST", "/candidate/contact-grants/" + grant_id + "/revoke")
    request(candidate, "POST", "/invitations/" + iid + "/accept")
    assert not request(employer, "GET", "/employer/candidates/" + cid)["contact_authorized"]
    report["checks"].append("contact revocation immediate; replayed acceptance never restores grant")
    pdf = candidate.get(BASE + "/candidate/profile.pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF-")
    report["checks"].append("real Unicode PDF export succeeds")
    imported = request(candidate, "POST", "/candidate/resume-import",
                       files={"file": ("synthetic-passport.pdf", pdf.content, "application/pdf")})
    assert imported["source"] == "SELF_DECLARED" and imported["persisted"] is False
    assert "ФСП ВЕКТОР" in imported["source_text"]
    for span in imported["source_spans"]:
        assert imported["source_text"][span["start"]:span["end"]] == span["quote"]
    after_import = request(candidate, "GET", "/candidate/profile")
    assert after_import["confirmed_grade"] == profile["confirmed_grade"]
    assert after_import["evidence"] == profile["evidence"]
    report["checks"].append("HTTP PDF reimport uses bounded child; exact Unicode spans; no persisted evidence or grade change")
    report["status"] = "passed"
    report["passed_checks"] = len(report["checks"])
    path = ROOT / "docs/audits/local-smoke.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

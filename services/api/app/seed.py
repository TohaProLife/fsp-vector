"""Idempotent original synthetic fixture import, explicitly local-demo only."""
import argparse
from datetime import datetime
from sqlalchemy import select
from .auth import digest, hash_password
from .config import settings
from .db import Base, SessionLocal, engine
from .models import Account, Candidate, Challenge, Company, Consent, FspRecord, Need, Notification, Vacancy

DEMO_PASSWORD = "VectorDemo2026!"


def seed_database(db, population=None):
    if not settings.local_demo:
        raise RuntimeError("Synthetic demo seed is forbidden outside LOCAL_DEMO")
    from .engines.seed import demo_seed, generate_population
    data = demo_seed()
    password = hash_password(DEMO_PASSWORD)
    company_ids = []
    for email, name, company_name in [("employer@vector.local", "Мария — команда найма", "Вектор Лаб"),
                                     ("employer2@vector.local", "Илья — вторая компания", "Спектр Технологии")]:
        account = db.scalar(select(Account).where(Account.email == email))
        if not account:
            account = Account(name=name, email=email, role="employer", email_verified=True, password_hash=password)
            db.add(account)
            db.flush()
            db.add(Consent(account_id=account.id, purpose="processing", granted=True))
        company = db.scalar(select(Company).where(Company.account_id == account.id))
        if not company:
            company = Company(account_id=account.id, name=company_name, city="Москва",
                description="Вымышленная продуктовая ИТ-компания локального стенда. Разрабатываем системы с ясными контрактами и проверяемыми результатами.",
                website="https://example.invalid", contact=email, team="Платформенная команда · 6 человек")
            db.add(company)
            db.flush()
        company_ids.append(company.id)
    fixtures = data["candidates"]
    if population and population > len(fixtures):
        fixtures += generate_population(population)[len(fixtures):]
    for item in fixtures:
        if db.scalar(select(Account).where(Account.email == item["email"])):
            continue
        account = Account(name=item["name"], email=item["email"], role="candidate", email_verified=True, password_hash=password)
        db.add(account)
        db.flush()
        when = datetime.fromisoformat(item["assessment_at"]) if item.get("assessment_at") else None
        category = {item["specialization"]: {"grade": item["confirmed_grade"], "score": item["score"],
            "confirmed_at": item.get("assessment_at"), "source": "SYNTHETIC_SEED", "calibration_status": "synthetic_fixture"}} if item.get("confirmed_grade") else {}
        candidate = Candidate(account_id=account.id, alias=item["alias"], title=item["title"], bio=item["bio"],
            city=item["city"], specialization=item["specialization"], declared_grade=item["declared_grade"],
            confirmed_grade=item["confirmed_grade"], score=item["score"], skills=item["skills"],
            preferences=item["preferences"], contacts={"email": item["email"]}, evidence=item["evidence"],
            fsp=item.get("fsp", {}), published=item.get("published", False), fixture=True,
            assessment_at=when, confirmed_categories=category)
        db.add(candidate)
        db.add(Consent(account_id=account.id, purpose="processing", granted=True))
        if candidate.published:
            db.add(Consent(account_id=account.id, purpose="publication", granted=True))
        if item["email"] == "candidate@vector.local":
            db.add(Notification(account_id=account.id, kind="onboarding", title="Ваш путь начинается с подтверждения компетенций",
                data={"href": "/workspace/assessment", "source": "synthetic_demo"}))
    for item in data["needs"]:
        if db.scalar(select(Need).where(Need.id == item["id"])):
            continue
        values = {key: value for key, value in item.items() if key != "id"}
        db.add(Need(id=item["id"], company_id=company_ids[0], data=values))
    for item in data["fsp_records"]:
        if not db.get(FspRecord, item["fsp_id"]):
            db.add(FspRecord(fsp_id=item["fsp_id"], email=item["email"], proof_hash=digest(item["proof_code"]), achievements=item["achievements"]))
    for item in data["challenges"]:
        if not db.get(Challenge, item["id"]):
            values = {key: value for key, value in item.items() if key not in {"id", "private_rubric"}}
            rubric = {"kind": "objective_declarative", "item": item["private_rubric"]}
            db.add(Challenge(id=item["id"], company_id=company_ids[0], data=values, rubric=rubric))
    for index, item in enumerate(data["needs"][:6]):
        vacancy_id = f"vacancy-fixture-{index+1}"
        if not db.get(Vacancy, vacancy_id):
            values = {key: value for key, value in item.items() if key != "id"}
            db.add(Vacancy(id=vacancy_id, company_id=company_ids[0], data=values,
                          salary_from=item["salary_from"], salary_to=item["salary_to"]))
    db.flush()
    return {"candidates": len(fixtures), "needs": len(data["needs"]), "source": "original_synthetic_fixtures"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--population", type=int, default=48)
    args = parser.parse_args()
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        result = seed_database(db, args.population)
        db.commit()
        print(result)


if __name__ == "__main__":
    main()

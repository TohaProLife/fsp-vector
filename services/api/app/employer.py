from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from .auth import EmployerUser
from .common import DB, audit, candidate_accessible, candidate_projection, company_dto, company_for, iso, prime_projection_access, require, rows, salary_valid
from .models import Account, Candidate, CompanyBlock, Consent, Invitation, MatchRun, Need, Vacancy

router = APIRouter(prefix="/employer", tags=["Employer & matching"])


@router.get("/company")
def company(account: EmployerUser, db: DB):
    return company_dto(company_for(db, account))


class CompanyPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    industry: str | None = Field(default=None, max_length=120)
    city: str | None = Field(default=None, max_length=120)
    website: str | None = Field(default=None, max_length=300)
    contact: str | None = Field(default=None, max_length=300)
    team: str | None = Field(default=None, max_length=3000)


@router.patch("/company")
def update_company(data: CompanyPatch, account: EmployerUser, db: DB):
    company = company_for(db, account)
    for key, value in data.model_dump(exclude_unset=True).items():
        require(value is not None, detail="Поля компании не могут быть null.")
        setattr(company, key, value.strip())
    audit(db, account, "company.updated", company.id)
    return company_dto(company)


class NeedData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=2, max_length=200)
    description: str = Field(default="", max_length=10000)
    specialization: str = Field(max_length=40)
    grade: str = Field(max_length=20)
    skills: list[str] = Field(default_factory=list, max_length=40)
    required_skills: list[str] = Field(default_factory=list, max_length=40)
    salary_from: int = Field(gt=0, le=10_000_000)
    salary_to: int = Field(gt=0, le=10_000_000)
    work_format: str = "remote"
    employment: str = "full_time"
    team: str = Field(default="", max_length=3000)


def validate_need(data):
    from .engines.assessment import catalog
    taxonomy = catalog()
    require(data["specialization"] in {item["id"] for item in taxonomy["specializations"]}, detail="Выберите доступную специализацию.")
    require(data["grade"] in {item["id"] if isinstance(item, dict) else item for item in taxonomy["grades"]}, detail="Выберите доступный грейд.")
    salary_valid(data)
    require(data["work_format"] in {"remote", "hybrid", "office", "any"}, detail="Неизвестный формат работы.")
    require(all(isinstance(value, str) and 0 < len(value) < 100 for value in data["skills"] + data["required_skills"]), detail="Проверьте навыки.")


def need_dto(row):
    return {"id": row.id, **row.data, "created_at": iso(row.created_at), "updated_at": iso(row.updated_at)}


def owned_need(db, company, need_id):
    row = db.get(Need, need_id)
    require(row is not None and row.company_id == company.id, 404, "NOT_FOUND", "Потребность не найдена.")
    return row


@router.get("/needs")
def needs(account: EmployerUser, db: DB):
    company = company_for(db, account)
    return rows([need_dto(row) for row in db.scalars(select(Need).where(Need.company_id == company.id).order_by(Need.created_at.desc()))])


@router.post("/needs", status_code=201)
def create_need(data: NeedData, account: EmployerUser, db: DB):
    company = company_for(db, account)
    values = data.model_dump()
    validate_need(values)
    row = Need(company_id=company.id, data=values)
    db.add(row)
    db.flush()
    audit(db, account, "need.created", row.id)
    return need_dto(row)


class Extract(BaseModel):
    text: str = Field(min_length=10, max_length=12000)


@router.post("/needs/extract")
def extract(data: Extract, account: EmployerUser, db: DB):
    from .engines.extraction import extract_need
    result = extract_need(data.text)
    return {**result, "persisted": False, "source": "dictionary_rules", "message": "Проверьте распознанные поля перед сохранением потребности."}


@router.get("/needs/{need_id}")
def need(need_id: str, account: EmployerUser, db: DB):
    return need_dto(owned_need(db, company_for(db, account), need_id))


@router.get("/needs/{need_id}/assessment-blueprint")
def need_assessment_blueprint(need_id: str, account: EmployerUser, db: DB):
    from .engines.assessment import need_blueprint
    row = owned_need(db, company_for(db, account), need_id)
    return {"need_id": row.id, **need_blueprint(row.data), "category_changes": False}


@router.patch("/needs/{need_id}")
def update_need(need_id: str, data: dict, account: EmployerUser, db: DB):
    row = owned_need(db, company_for(db, account), need_id)
    merged = NeedData.model_validate({**row.data, **data}).model_dump()
    validate_need(merged)
    row.data = merged
    audit(db, account, "need.updated", row.id)
    return need_dto(row)


def eligible(db, filters=None, company=None):
    filters = filters or {}
    latest_processing = select(Consent.granted).where(Consent.account_id == Candidate.account_id,
        Consent.purpose == "processing").order_by(Consent.created_at.desc()).limit(1).scalar_subquery()
    candidates = db.scalars(select(Candidate).join(Account, Account.id == Candidate.account_id).where(
        Candidate.published.is_(True), Candidate.confirmed_grade.is_not(None), Account.email_verified.is_(True),
        latest_processing.is_(True))).all()
    if company:
        blocked = set(db.scalars(select(CompanyBlock.candidate_id).where(CompanyBlock.company_id == company.id)).all())
        candidates = [item for item in candidates if item.id not in blocked]
    result = []
    for candidate in candidates:
        if filters.get("specialization") and candidate.specialization != filters["specialization"]:
            continue
        if filters.get("grade") and candidate.confirmed_grade != filters["grade"]:
            continue
        skill = filters.get("skill")
        if skill and skill.casefold() not in {s.casefold() for s in candidate.skills}:
            continue
        if filters.get("skills") and not {s.casefold() for s in filters["skills"]} <= {s.casefold() for s in candidate.skills}:
            continue
        if filters.get("fsp_only") and candidate.fsp.get("status") not in {"sync_ok", "verified_demo", "verified", "ok"}:
            continue
        fmt = filters.get("work_format")
        if fmt and fmt != "any" and candidate.preferences.get("work_format") not in {fmt, "any", None}:
            continue
        q = filters.get("q", "").casefold()
        if q and q not in " ".join([candidate.alias, candidate.title, candidate.specialization or "", *candidate.skills]).casefold():
            continue
        result.append(candidate)
    # Request-local bulk rights snapshot; never reused across requests/company scopes.
    prime_projection_access(db, result, company)
    return result


@router.get("/candidates")
def candidates(account: EmployerUser, db: DB, q: str = "", specialization: str | None = None,
               grade: str | None = None, skill: str | None = None, fsp_only: bool = False,
               work_format: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(24, ge=1, le=100)):
    company = company_for(db, account)
    selected = eligible(db, {"q": q, "specialization": specialization, "grade": grade, "skill": skill,
                              "fsp_only": fsp_only, "work_format": work_format}, company)
    selected.sort(key=lambda row: (row.score or 0, row.alias), reverse=True)
    return {"items": [candidate_projection(db, row, company) for row in selected[(page-1)*page_size:page*page_size]],
            "total": len(selected), "page": page, "page_size": page_size}


@router.get("/categories")
def categories(account: EmployerUser, db: DB):
    counts = {}
    for row in eligible(db, company=company_for(db, account)):
        key = f"{row.specialization}:{row.confirmed_grade}"
        counts.setdefault(key, {"id": key, "specialization": row.specialization, "grade": row.confirmed_grade,
                                "label": f"{row.specialization} · {row.confirmed_grade}", "count": 0})["count"] += 1
    return rows(list(counts.values()))


@router.get("/candidates/{candidate_id}")
def candidate(candidate_id: str, account: EmployerUser, db: DB):
    company = company_for(db, account)
    row = db.get(Candidate, candidate_id)
    blocked = db.scalar(select(CompanyBlock).where(CompanyBlock.company_id == company.id, CompanyBlock.candidate_id == candidate_id))
    require(candidate_accessible(db, row, company) and not blocked,
            404, "NOT_FOUND", "Карточка недоступна или снята с публикации.")
    return candidate_projection(db, row, company)


class MatchData(BaseModel):
    need_id: str
    filters: dict = Field(default_factory=dict)


class MatchFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    q: str = Field(default="",max_length=200)
    specialization: str | None = Field(default=None,max_length=40)
    grade: str | None = Field(default=None,max_length=20)
    skill: str | None = Field(default=None,max_length=80)
    skills: list[str] = Field(default_factory=list,max_length=40)
    fsp_only: bool = False
    work_format: str | None = Field(default=None,max_length=20)


def create_match(db, company, need, filters, parent_id=None, need_snapshot=None):
    from .engines.matching import ALGORITHM_VERSION, rank_candidates
    filters = MatchFilters.model_validate(filters).model_dump(exclude_unset=True,exclude_none=True)
    projections = [candidate_projection(db, row, company=company) for row in eligible(db, filters, company)]
    # Strip presentation contacts even if caller ever passes a richer projection.
    for projection in projections:
        projection.pop("contacts", None)
        projection.pop("name", None)
        projection.pop("bio", None)
    context = need_snapshot if need_snapshot is not None else need.data
    ranked = rank_candidates(context, projections, company_id=company.id)
    if isinstance(ranked, dict):
        ranked = ranked.get("items", [])
    algorithm = ranked[0].get("algorithm_version", ALGORITHM_VERSION) if ranked else ALGORITHM_VERSION
    row = MatchRun(company_id=company.id, need_id=need.id, parent_id=parent_id, filters=filters, algorithm_version=algorithm,
                   need_snapshot=context, results=ranked)
    db.add(row)
    db.flush()
    return row


def match_dto(db, row, company):
    items = []
    candidate_ids = {ranked.get("candidate_id") or ranked.get("candidate", {}).get("id") for ranked in row.results}
    population = db.scalars(select(Candidate).where(Candidate.id.in_(candidate_ids))
                            .execution_options(populate_existing=True)).all() if candidate_ids else []
    prime_projection_access(db, population, company)
    by_id = {candidate.id: candidate for candidate in population}
    for ranked in row.results:
        candidate_id = ranked.get("candidate_id") or ranked.get("candidate", {}).get("id")
        candidate = by_id.get(candidate_id)
        # Permission is rechecked on every saved run read, including after revocation.
        if not candidate_accessible(db, candidate, company):
            continue
        safe = {key: ranked.get(key) for key in ("score", "breakdown", "reasons", "gaps", "semantic_status")}
        safe["candidate"] = candidate_projection(db, candidate, company)
        items.append(safe)
    return {"id": row.id, "need_id": row.need_id, "parent_id": row.parent_id,
            "algorithm_version": row.algorithm_version, "items": items, "total": len(items),
            "filters": row.filters, "need": row.need_snapshot, "created_at": iso(row.created_at),
            "score_kind": "ranking_index_not_probability"}


@router.post("/matches", status_code=201)
def match(data: MatchData, account: EmployerUser, db: DB):
    company = company_for(db, account)
    row = create_match(db, company, owned_need(db, company, data.need_id), data.filters)
    audit(db, account, "matching.created", row.id, {"algorithm": row.algorithm_version})
    return match_dto(db, row, company)


@router.get("/matches")
def match_runs(account: EmployerUser, db: DB):
    company = company_for(db, account)
    return rows([{"id": row.id, "need_id": row.need_id, "title": row.need_snapshot.get("title"),
        "created_at": iso(row.created_at)} for row in db.scalars(select(MatchRun).where(MatchRun.company_id == company.id).order_by(MatchRun.created_at.desc()))])


def owned_match(db, company, match_id):
    row = db.get(MatchRun, match_id)
    require(row is not None and row.company_id == company.id, 404, "NOT_FOUND", "Подборка не найдена.")
    return row


@router.get("/matches/{match_id}")
def saved_match(match_id: str, account: EmployerUser, db: DB):
    company = company_for(db, account)
    return match_dto(db, owned_match(db, company, match_id), company)


@router.post("/matches/{match_id}/refine", status_code=201)
def refine(match_id: str, data: dict, account: EmployerUser, db: DB):
    company = company_for(db, account)
    parent = owned_match(db, company, match_id)
    filters = {**parent.filters, **data.get("filters", data)}
    row = create_match(db, company, owned_need(db, company, parent.need_id), filters, parent.id,
                       need_snapshot=parent.need_snapshot)
    audit(db, account, "matching.refined", row.id, {"parent_id": parent.id})
    return match_dto(db, row, company)


@router.get("/dashboard")
def dashboard(account: EmployerUser, db: DB):
    from .hiring import invitation_dto
    company = company_for(db, account)
    needs = db.scalars(select(Need).where(Need.company_id == company.id).order_by(Need.created_at.desc())).all()
    invitations = db.scalars(select(Invitation).where(Invitation.company_id == company.id).order_by(Invitation.created_at.desc())).all()
    vacancies = db.scalars(select(Vacancy).where(Vacancy.company_id == company.id)).all()
    return {"company": company_dto(company), "stats": {"candidates": len(eligible(db,company=company)), "needs": len(needs),
        "invitations": len(invitations), "accepted": sum(row.status == "accepted" for row in invitations), "vacancies": len(vacancies)},
        "recent_invitations": [invitation_dto(db, row, account) for row in invitations[:6]],
        "needs": [need_dto(row) for row in needs[:6]]}

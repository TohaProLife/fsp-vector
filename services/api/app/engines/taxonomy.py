"""Versioned, deliberately narrow skill map. A grade does not imply every technology."""

TAXONOMY_VERSION = "vector-taxonomy-1"
GRADES = ("intern", "junior", "middle", "senior")
GRADE_LABELS = {"intern": "Стажёр", "junior": "Junior", "middle": "Middle", "senior": "Senior"}
SPECIALIZATIONS = {
    "backend": {"label": "Backend", "competencies": ["api", "sql", "reliability", "testing"], "stacks": ["Python / SQL / API", "TypeScript / SQL / API"]},
    "frontend": {"label": "Frontend", "competencies": ["javascript", "state", "accessibility", "web_security"], "stacks": ["JavaScript / React"]},
    "qa": {"label": "QA", "competencies": ["test_design", "api", "sql", "reliability"], "stacks": ["API / SQL / test design"]},
    "devops": {"label": "DevOps / SRE", "competencies": ["observability", "containers", "networking", "reliability"], "stacks": ["Linux / containers / SRE"]},
    "data": {"label": "Data analytics", "competencies": ["sql", "statistics", "data_quality", "interpretation"], "stacks": ["SQL / statistics"]},
    "security": {"label": "Security", "competencies": ["web_security", "authorization", "cryptography", "incident_response"], "stacks": ["Web / secure design"]},
}
COMPETENCY_LABELS = {
    "api": "Контракты API", "sql": "Работа с данными / SQL", "reliability": "Надёжность и согласованность",
    "testing": "Проверка инвариантов", "javascript": "JavaScript", "state": "Состояние интерфейса",
    "accessibility": "Доступность", "web_security": "Безопасность web", "test_design": "Проектирование проверок",
    "observability": "Наблюдаемость", "containers": "Контейнеры", "networking": "Сети",
    "statistics": "Статистика", "data_quality": "Качество данных", "interpretation": "Интерпретация",
    "authorization": "Авторизация", "cryptography": "Криптографические примитивы", "incident_response": "Разбор инцидентов",
}
SKILL_ALIASES = {
    "python": "Python", "питон": "Python", "typescript": "TypeScript", "ts": "TypeScript", "javascript": "JavaScript", "js": "JavaScript",
    "react": "React", "реакт": "React", "sql": "SQL", "postgresql": "PostgreSQL", "postgres": "PostgreSQL",
    "fastapi": "FastAPI", "django": "Django", "node.js": "Node.js", "nodejs": "Node.js", "docker": "Docker",
    "kubernetes": "Kubernetes", "k8s": "Kubernetes", "linux": "Linux", "git": "Git", "redis": "Redis", "kafka": "Kafka",
    "rest": "API", "rest api": "API", "rest-api": "API", "restful api": "API", "http api": "API", "api": "API", "http": "HTTP", "pytest": "pytest", "playwright": "Playwright", "pandas": "pandas",
    "prometheus": "Prometheus", "grafana": "Grafana", "terraform": "Terraform", "statistics": "Статистика", "статистика": "Статистика",
    "wcag": "Доступность", "a11y": "Доступность", "oauth": "OAuth", "oidc": "OIDC", "ctf": "CTF", "owasp": "OWASP",
    "unit": "Unit testing", "тестирование": "Test design", "ci/cd": "CI/CD", "slo": "SLO", "идемпотентность": "Идемпотентность",
}
COMPETENCY_SKILLS = {
    "api": ["API"], "sql": ["SQL"], "reliability": ["Идемпотентность"], "testing": ["Unit testing"],
    "javascript": ["JavaScript concepts"], "state": ["UI state"], "accessibility": ["Доступность"], "web_security": ["Web security"],
    "test_design": ["Test design"], "observability": ["SLO"], "containers": ["Container concepts"], "networking": ["HTTP concepts"],
    "statistics": ["Статистика"], "data_quality": ["Data quality"], "interpretation": ["Data interpretation"],
    "authorization": ["Authorization"], "cryptography": ["Cryptography concepts"], "incident_response": ["Incident response"],
}
CANONICAL_VALUES={known.casefold():known for known in set(SKILL_ALIASES.values()) | {skill for values in COMPETENCY_SKILLS.values() for skill in values}}


def canonical_skill(skill: str) -> str:
    value = " ".join(str(skill).split())
    canonical=SKILL_ALIASES.get(value.casefold())
    if canonical: return canonical
    return CANONICAL_VALUES.get(value.casefold(),value)


def normalize_specialization(value: str) -> str:
    normalized = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    return {"data_analytics": "data", "analytics": "data", "data_analyst": "data", "sre": "devops", "devops/sre": "devops", "qa_engineer": "qa", "security/ctf": "security"}.get(normalized, normalized)


def normalize_grade(value: str) -> str:
    normalized = str(value).strip().lower()
    return {"trainee": "intern", "стажёр": "intern", "стажер": "intern", "джуниор": "junior", "мидл": "middle", "сеньор": "senior"}.get(normalized, normalized)

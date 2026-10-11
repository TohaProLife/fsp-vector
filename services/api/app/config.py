import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./vector.db")
    local_demo: bool = os.getenv("LOCAL_DEMO", "true").lower() == "true"
    cookie_secure: bool = os.getenv("COOKIE_SECURE", "false").lower() == "true"
    frontend_url: str = os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/")
    auto_seed: bool = os.getenv("AUTO_SEED", "true" if os.getenv("LOCAL_DEMO", "true").lower() == "true" else "false").lower() == "true"
    session_days: int = 7
    upload_limit: int = 3 * 1024 * 1024
    storage_dir: Path = Path(os.getenv("STORAGE_DIR", "./storage"))
    smtp_host: str = os.getenv("SMTP_HOST", "")
    smtp_port: int = int(os.getenv("SMTP_PORT", "1025"))
    smtp_sender: str = os.getenv("SMTP_SENDER", "noreply@vector.local")
    ats_webhook_url: str = os.getenv("ATS_WEBHOOK_URL", "")
    ats_webhook_secret: str = os.getenv("ATS_WEBHOOK_SECRET", "")
    auto_create_schema: bool = os.getenv("AUTO_CREATE_SCHEMA", "true" if os.getenv("LOCAL_DEMO", "true").lower() == "true" else "false").lower() == "true"


settings = Settings()


def validate_runtime_configuration(config: Settings):
    """Reject unsafe deployment modes without exposing configuration secrets."""
    frontend = urlparse(config.frontend_url)
    problems = []
    if config.local_demo:
        if frontend.hostname not in {"localhost", "127.0.0.1", "::1"}:
            problems.append("LOCAL_DEMO requires a loopback frontend")
    else:
        if config.auto_seed:
            problems.append("AUTO_SEED must be false")
        if config.auto_create_schema:
            problems.append("AUTO_CREATE_SCHEMA must be false; run Alembic")
        if not config.cookie_secure:
            problems.append("COOKIE_SECURE must be true")
        if frontend.scheme != "https" or not frontend.hostname or frontend.username or frontend.password:
            problems.append("FRONTEND_URL must be HTTPS")
        if not config.database_url.startswith("postgresql"):
            problems.append("PostgreSQL is required")
        if not config.smtp_host:
            problems.append("SMTP transport is required")
    if problems:
        raise RuntimeError("Unsafe runtime configuration: " + "; ".join(problems))

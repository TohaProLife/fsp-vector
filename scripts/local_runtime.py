"""Project-scoped PostgreSQL and Keycloak lifecycle. Secrets remain in .local/."""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local"
RUNTIME = ROOT / ".runtime"
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def load_config() -> dict:
    LOCAL.mkdir(exist_ok=True)
    path = LOCAL / "runtime.json"
    if not path.exists():
        data = {
            "pg_port": 55432, "pg_admin_password": secrets.token_hex(24),
            "pg_app_password": secrets.token_hex(24), "oidc_client_secret": secrets.token_hex(32),
            "keycloak_admin_password": secrets.token_hex(24), "session_secret": secrets.token_hex(32),
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    data = json.loads(path.read_text(encoding="utf-8"))
    if "ats_webhook_secret" not in data:
        data["ats_webhook_secret"] = secrets.token_hex(32)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def is_listening(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def run(command: list[str], *, env: dict | None = None, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(command, check=True, env=env, creationflags=CREATE_NO_WINDOW, **kwargs)


def start_postgres(config: dict) -> None:
    binary = RUNTIME / "pgsql" / "bin"
    if not (binary / "pg_ctl.exe").exists():
        raise RuntimeError("PostgreSQL runtime is missing; run scripts/bootstrap_runtime.py")
    data = LOCAL / "pgdata"
    env = os.environ.copy()
    env["PGPASSWORD"] = config["pg_admin_password"]
    if not (data / "PG_VERSION").exists():
        password = LOCAL / "pg-init-password.txt"
        password.write_text(config["pg_admin_password"], encoding="ascii")
        try:
            run([str(binary / "initdb.exe"), "-D", str(data), "-U", "vector_admin", "--pwfile", str(password),
                 "--auth=scram-sha-256", "--encoding=UTF8", "--locale=C"], env=env, stdout=subprocess.DEVNULL)
        finally:
            password.unlink(missing_ok=True)
    if not is_listening(config["pg_port"]):
        run([str(binary / "pg_ctl.exe"), "start", "-D", str(data), "-l", str(LOCAL / "postgres.log"),
             "-o", f"-p {config['pg_port']} -h 127.0.0.1", "-w", "-t", "45"], env=env)
    psql = [str(binary / "psql.exe"), "-X", "-h", "127.0.0.1", "-p", str(config["pg_port"]),
            "-U", "vector_admin", "-d", "postgres", "-v", "ON_ERROR_STOP=1"]
    exists = run(psql + ["-Atc", "SELECT 1 FROM pg_roles WHERE rolname='vector'"], env=env, capture_output=True, text=True)
    if exists.stdout.strip() != "1":
        # Hex generated locally; never interpolated from user or network input.
        run(psql + ["-c", f"CREATE ROLE vector LOGIN PASSWORD '{config['pg_app_password']}' NOSUPERUSER NOCREATEDB NOCREATEROLE"],
            env=env, stdout=subprocess.DEVNULL)
    exists = run(psql + ["-Atc", "SELECT 1 FROM pg_database WHERE datname='vector'"], env=env, capture_output=True, text=True)
    if exists.stdout.strip() != "1":
        run(psql + ["-c", "CREATE DATABASE vector OWNER vector"], env=env, stdout=subprocess.DEVNULL)
    print(f"PostgreSQL ready at 127.0.0.1:{config['pg_port']} (non-superuser app role)", flush=True)


def application_env(config: dict) -> dict[str, str]:
    env = os.environ.copy()
    env.update({
        "DATABASE_URL": f"postgresql+psycopg://vector:{config['pg_app_password']}@127.0.0.1:{config['pg_port']}/vector",
        "LOCAL_DEMO": "true", "COOKIE_SECURE": "false", "AUTO_SEED": "true",
        "FRONTEND_URL": "http://localhost:3000", "API_ORIGIN": "http://127.0.0.1:8000",
        "STORAGE_DIR": str(LOCAL / "storage"), "SESSION_SECRET": config["session_secret"],
        "OIDC_ISSUER": "http://localhost:8081/realms/vector", "OIDC_CLIENT_ID": "vector-web",
        "OIDC_CLIENT_SECRET": config["oidc_client_secret"],
        "OIDC_REDIRECT_URI": "http://localhost:3000/api/v1/auth/oidc/callback",
        "PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1", "NEXT_TELEMETRY_DISABLED": "1",
        "SMTP_HOST": "127.0.0.1", "SMTP_PORT": "1025", "SMTP_SENDER": "noreply@vector.local",
        "ATS_WEBHOOK_URL": "http://127.0.0.1:8090/events", "ATS_WEBHOOK_SECRET": config["ats_webhook_secret"],
        "AUTO_CREATE_SCHEMA": "false", "MATCH_SEMANTIC_ENABLED": "false",
    })
    return env


def start_mailpit() -> subprocess.Popen | None:
    if is_listening(1025):
        return None
    binary = RUNTIME / "mailpit.exe"
    if not binary.exists():
        raise RuntimeError("Mailpit runtime missing; run scripts/bootstrap_runtime.py")
    log = (LOCAL / "mailpit.log").open("ab")
    process = subprocess.Popen([str(binary), "--listen", "127.0.0.1:8025", "--smtp", "127.0.0.1:1025", "--database", str(LOCAL / "mailpit.db")],
                               cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=log, creationflags=CREATE_NO_WINDOW)
    (LOCAL / "mailpit.pid").write_text(str(process.pid), encoding="ascii")
    print("Local mail captured at http://localhost:8025", flush=True)
    return process


def start_keycloak(config: dict) -> subprocess.Popen | None:
    if is_listening(8081):
        return None
    directory = RUNTIME / "keycloak-26.8.0"
    java = next(RUNTIME.glob("jdk-25*-jre"), None)
    if not java or not (directory / "bin" / "kc.bat").exists():
        raise RuntimeError("Keycloak/Java runtime missing")
    template = ROOT / "deploy" / "keycloak" / "vector-realm.template.json"
    payload = template.read_text(encoding="utf-8").replace("__CLIENT_SECRET__", config["oidc_client_secret"])
    imports = directory / "data" / "import"
    imports.mkdir(parents=True, exist_ok=True)
    (imports / "vector-realm.json").write_text(payload, encoding="utf-8")
    env = os.environ.copy()
    env.update({"JAVA_HOME": str(java), "KC_BOOTSTRAP_ADMIN_USERNAME": "vector-admin",
                "KC_BOOTSTRAP_ADMIN_PASSWORD": config["keycloak_admin_password"],
                "JAVA_OPTS_APPEND": "-Xms128m -Xmx512m"})
    log = (LOCAL / "keycloak.log").open("ab")
    process = subprocess.Popen([str(directory / "bin" / "kc.bat"), "start-dev", "--import-realm",
                                "--http-host=127.0.0.1", "--http-port=8081", "--hostname=http://localhost:8081"],
                               cwd=directory, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                               creationflags=CREATE_NO_WINDOW)
    (LOCAL / "keycloak.pid").write_text(str(process.pid), encoding="ascii")
    print("Keycloak starting at http://localhost:8081; log .local/keycloak.log", flush=True)
    return process


if __name__ == "__main__":
    config = load_config()
    start_postgres(config)

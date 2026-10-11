"""Start the complete local FSP Vector workspace; all logs/secrets stay private."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import urllib.request

from local_runtime import ROOT, LOCAL, CREATE_NO_WINDOW, application_env, is_listening, load_config, start_keycloak, start_mailpit, start_postgres
from local_processes import capture_process, spawn_owned, terminate_owned


def wait_ready(url: str, process: subprocess.Popen, timeout: int = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Process exited ({process.returncode}); see .local logs")
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.5)
    raise RuntimeError(f"Readiness deadline exceeded for {url}")


def spawn(name: str, command: list[str], cwd: Path, env: dict) -> subprocess.Popen:
    log = (LOCAL / f"{name}.log").open("ab")
    return spawn_owned(command, workspace=ROOT, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                       creationflags=CREATE_NO_WINDOW)


def terminate_tree(process: subprocess.Popen) -> None:
    terminate_owned(process, ROOT)


def main() -> None:
    startup_clock = time.monotonic()
    startup_epoch = time.time()
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-identity", action="store_true", help="Password/email auth stays available")
    parser.add_argument("--portable", action="store_true", help="Explicit SQLite fallback")
    parser.add_argument("--production-web", action="store_true", help="Run prebuilt Next production server")
    args = parser.parse_args()
    config = load_config()
    env = application_env(config)
    if args.portable:
        env["DATABASE_URL"] = "sqlite:///" + str(LOCAL / "vector.sqlite3").replace("\\", "/")
    else:
        start_postgres(config)
    start_mailpit()
    if not args.no_identity:
        start_keycloak(config)
    else:
        env["OIDC_ISSUER"] = ""
        env["OIDC_CLIENT_SECRET"] = ""
    python = ROOT / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    node = shutil.which("node")
    if not python.exists() or not node:
        raise RuntimeError("Run scripts/setup.ps1 first (Python venv and Node.js are required)")
    for port in (8000, 3000):
        if is_listening(port):
            raise RuntimeError(f"Port {port} is in use; stop the prior project instance before starting")
    processes = []
    try:
        subprocess.run([str(python), "-m", "alembic", "upgrade", "head"], cwd=ROOT / "services/api", env=env, check=True)
        receiver = spawn("ats", [str(python), "-m", "uvicorn", "services.integrations.receiver:app", "--host", "127.0.0.1", "--port", "8090", "--no-access-log"], ROOT, env)
        processes.append(receiver)
        wait_ready("http://127.0.0.1:8090/health", receiver)
        api = spawn("api", [str(python), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000", "--no-access-log"],
                    ROOT / "services/api", env)
        processes.append(api)
        wait_ready("http://127.0.0.1:8000/ready", api)
        worker_module = ROOT / "services/api/app/worker.py"
        if worker_module.exists():
            processes.append(spawn("worker", [str(python), "-m", "app.worker"], ROOT / "services/api", env))
        next_bin = ROOT / "apps/web/node_modules/next/dist/bin/next"
        mode = "start" if args.production_web else "dev"
        web = spawn("web", [node, str(next_bin), mode, "--hostname", "127.0.0.1", "--port", "3000"], ROOT / "apps/web", env)
        processes.append(web)
        wait_ready("http://127.0.0.1:3000", web, timeout=90)
        supervisor_id = __import__("os").getpid()
        supervisor_identity = capture_process(supervisor_id, ROOT, startup_epoch, supervisor=True)
        identities = [identity for identity in [supervisor_identity] +
                      [getattr(process, "_vector_identity", None) for process in processes] if identity]
        (LOCAL / "processes.json").write_text(json.dumps({"supervisor": supervisor_id, "children": [p.pid for p in processes],
              "identities": identities,
              "workspace": str(ROOT), "started_at": startup_epoch, "ready_at": time.time(),
              "startup_seconds": round(time.monotonic() - startup_clock, 3),
              "startup_scope": "application readiness with already provisioned local runtimes; excludes setup and web build"}), encoding="utf-8")
        print("FSP Vector is running at http://localhost:3000", flush=True)
        print("API / OpenAPI: http://localhost:8000/docs", flush=True)
        print("Identity: http://localhost:8081/realms/vector/account", flush=True)
        print("Synthetic demo: candidate@vector.local / employer@vector.local; password VectorDemo2026!", flush=True)
        print("Email inbox: http://localhost:8025 · Signed local ATS: http://localhost:8090/health", flush=True)
        print("Logs: .local/ . Press Ctrl+C to stop web/API/worker/ATS; PostgreSQL and identity remain available.", flush=True)
        while all(process.poll() is None for process in processes):
            time.sleep(1)
        raise RuntimeError("A service exited unexpectedly; inspect .local logs")
    except KeyboardInterrupt:
        print("Stopping FSP Vector application services", flush=True)
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                terminate_tree(process)
        for process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
        (LOCAL / "processes.json").unlink(missing_ok=True)


if __name__ == "__main__":
    main()

"""Consistent private application backups; restore only to a new project-owned DB."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from uuid import uuid4

import psycopg
from psycopg import sql, IsolationLevel

from local_runtime import ROOT, LOCAL, RUNTIME, CREATE_NO_WINDOW, load_config

BACKUPS = LOCAL / "backups"


def binary(name: str) -> str:
    bundled = RUNTIME / "pgsql/bin" / (name + (".exe" if os.name == "nt" else ""))
    result = str(bundled) if bundled.exists() else shutil.which(name)
    if not result:
        raise RuntimeError(f"Missing PostgreSQL utility {name}")
    return result


def connect(config: dict, database: str, *, admin: bool = False, autocommit: bool = False):
    return psycopg.connect(host="127.0.0.1", port=config["pg_port"], dbname=database,
                          user="vector_admin" if admin else "vector",
                          password=config["pg_admin_password"] if admin else config["pg_app_password"],
                          connect_timeout=5, autocommit=autocommit)


def table_counts(connection) -> dict[str, int]:
    names = connection.execute("SELECT table_name FROM information_schema.tables "
                               "WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY table_name").fetchall()
    return {name: connection.execute(sql.SQL("SELECT count(*) FROM public.{}").format(sql.Identifier(name))).fetchone()[0]
            for (name,) in names}


def command(config: dict, program: str, database: str, arguments: list[str]) -> None:
    env = os.environ.copy()
    env["PGPASSWORD"] = config["pg_app_password"]
    process = subprocess.run([binary(program), "--host=127.0.0.1", "--port=" + str(config["pg_port"]),
                              "--username=vector", "--dbname=" + database, *arguments], env=env,
                             capture_output=True, creationflags=CREATE_NO_WINDOW, timeout=120)
    if process.returncode:
        # Utility diagnostics can echo data or connection details. Keep those private.
        diagnostic = BACKUPS / (program + "-failure.log")
        diagnostic.write_bytes(process.stderr)
        raise RuntimeError(f"{program} failed; private diagnostic: .local/backups/{diagnostic.name}")


def backup(config: dict) -> Path:
    BACKUPS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = BACKUPS / f"vector-{stamp}-{uuid4().hex[:8]}.dump"
    with connect(config, "vector") as connection:
        connection.isolation_level = IsolationLevel.REPEATABLE_READ
        connection.read_only = True
        snapshot = connection.execute("SELECT pg_export_snapshot()").fetchone()[0]
        counts = table_counts(connection)
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        command(config, "pg_dump", "vector", ["--format=custom", "--no-owner", "--no-privileges",
                                               "--snapshot=" + snapshot, "--file=" + str(path)])
    manifest = {"format": "vector-private-backup-1", "created_at": datetime.now(timezone.utc).isoformat(),
                "database_scope": "application_only", "schema_revision": revision, "table_counts": counts,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    path.with_suffix(".dump.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    return path


def managed_backup(path: Path) -> tuple[Path, dict]:
    target = path.resolve(strict=True)
    if target.parent != BACKUPS.resolve() or target.suffix != ".dump":
        raise RuntimeError("Use only a managed private backup in .local/backups")
    manifest = json.loads(target.with_suffix(".dump.json").read_text(encoding="utf-8"))
    if manifest.get("format") != "vector-private-backup-1" or hashlib.sha256(target.read_bytes()).hexdigest() != manifest["sha256"]:
        raise RuntimeError("Backup integrity check failed")
    return target, manifest


def restore(config: dict, path: Path, *, keep: bool) -> dict:
    target, manifest = managed_backup(path)
    database = "vector_restore_audit_" + uuid4().hex
    if not re.fullmatch(r"vector_restore_audit_[a-f0-9]{32}", database):
        raise RuntimeError("Invalid isolated restore target")
    created = False
    verified = False
    try:
        with connect(config, "postgres", admin=True, autocommit=True) as connection:
            connection.execute(sql.SQL("CREATE DATABASE {} OWNER vector").format(sql.Identifier(database)))
            created = True
        command(config, "pg_restore", database, ["--no-owner", "--no-privileges", "--exit-on-error", str(target)])
        with connect(config, database) as connection:
            counts = table_counts(connection)
            revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        if counts != manifest["table_counts"] or revision != manifest["schema_revision"]:
            raise RuntimeError("Restored schema or row counts differ from the consistent snapshot")
        verified = True
        return {"status": "passed", "source_scope": "private_application_database", "consistent_snapshot": True,
                "restore_target": "new_isolated_database", "primary_database_modified": False,
                "tables_checked": len(counts), "rows_checked": sum(counts.values()), "schema_revision": revision,
                "backup_sha256": manifest["sha256"], "retained_database": database if keep else None,
                "identity_database_included": False}
    finally:
        if created and (not keep or not verified):
            # Only this exact generated and created database may be dropped.
            with connect(config, "postgres", admin=True, autocommit=True) as connection:
                connection.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("backup")
    for action in ("verify", "restore-new"):
        p = sub.add_parser(action)
        p.add_argument("path", type=Path)
    audit = sub.add_parser("audit")
    audit.add_argument("--report", type=Path, default=ROOT / "docs/audits/backup-restore.json")
    args = parser.parse_args()
    config = load_config()
    if args.action == "backup":
        print(backup(config))
        return
    path = backup(config) if args.action == "audit" else args.path
    result = restore(config, path, keep=args.action == "restore-new")
    if args.action == "audit":
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        detail = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
        print(f"Snapshot operation stopped: {detail}", file=sys.stderr)
        raise SystemExit(1)

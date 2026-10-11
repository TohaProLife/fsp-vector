"""Runsc-only Docker adapter. Docker access belongs on a separate disposable Linux VM.

No automatic pull, native execution, shell interpolation, privileged mode or runc
fallback exists. The checker and expected answers run outside the sandbox.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from uuid import uuid4
from .tasks import TASKS, expected

MAX_OUTPUT = 64 * 1024
WALL_SECONDS = 20
SEMAPHORE = threading.BoundedSemaphore(2)
STATUS_LOCK = threading.Lock()
STATUS_CACHE = (0.0, {})

PYTHON_HARNESS = """import importlib.util, json, sys
spec=importlib.util.spec_from_file_location('candidate', '/task/submission.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
data=json.loads(sys.stdin.read())
for item in data:
    print(json.dumps(module.solve(item), ensure_ascii=False, allow_nan=False), flush=True)
"""
JS_HARNESS = """const fs = require('node:fs');
const { solve } = require('/task/submission.cjs');
const cases = JSON.parse(fs.readFileSync(0, 'utf8'));
for (const item of cases) console.log(JSON.stringify(solve(item)));
"""


def image_for(language: str) -> str:
    key = {"python": "JUDGE_PYTHON_IMAGE", "javascript": "JUDGE_NODE_IMAGE"}.get(language)
    if not key:
        raise ValueError("Unsupported language")
    image = os.getenv(key, "")
    if not re.fullmatch(r"[a-zA-Z0-9./:_-]+@sha256:[a-f0-9]{64}", image):
        raise RuntimeError("A provisioned digest-pinned image is required")
    return image


def probe_readiness() -> dict:
    if sys.platform != "linux" or not shutil.which("docker"):
        return {"available": False, "reason": "linux_docker_runsc_required"}
    try:
        images = [image_for(language) for language in ("python", "javascript")]
        info = subprocess.run(["docker", "info", "--format", "{{json .Runtimes}}"],
                              capture_output=True, timeout=5, check=True, text=True)
        if "runsc" not in json.loads(info.stdout):
            raise RuntimeError("Runsc runtime not installed")
        for image in images:
            subprocess.run(["docker", "image", "inspect", image], capture_output=True,
                           timeout=5, check=True)
        return {"available": True, "isolation": "gvisor_runsc", "network": "none",
                "languages": ["python", "javascript"], "limits": {"memory_mb": 256,
                    "cpus": 1, "pids": 32, "wall_seconds": WALL_SECONDS, "output_bytes": MAX_OUTPUT}}
    except (ValueError, RuntimeError, subprocess.SubprocessError, OSError):
        return {"available": False, "reason": "sandbox_or_pinned_images_unavailable"}


def readiness() -> dict:
    global STATUS_CACHE
    with STATUS_LOCK:
        if time.monotonic() - STATUS_CACHE[0] > 5:
            STATUS_CACHE = (time.monotonic(), probe_readiness())
        return dict(STATUS_CACHE[1])


def command(name: str, directory: Path, language: str) -> list[str]:
    image = image_for(language)
    executable = ["python", "-I", "-B", "/task/harness.py"] if language == "python" else ["node", "/task/harness.cjs"]
    return ["docker", "run", "--name", name, "--rm", "--pull=never", "--runtime=runsc",
            "--network=none", "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges:true",
            "--user=65534:65534", "--pids-limit=32", "--memory=256m", "--memory-swap=256m",
            "--cpus=1", "--ulimit=nofile=64:64", "--ulimit=fsize=1048576:1048576",
            "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=16m", "--log-driver=none",
            "--mount", f"type=bind,src={directory},dst=/task,readonly", "-i", image, *executable]


def strict_json_equal(value, reference) -> bool:
    # JSON booleans must never count as integers through Python's True == 1.
    return json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":")) == json.dumps(reference, sort_keys=True, allow_nan=False, separators=(",", ":"))


def run_submission(task_id: str, language: str, source: str) -> dict:
    if task_id not in TASKS or language not in {"python", "javascript"} or len(source.encode()) > 32_000:
        raise ValueError("Invalid submission")
    if not readiness()["available"]:
        return {"status": "unavailable", "passed": False, "changes_category": False}
    if not SEMAPHORE.acquire(blocking=False):
        return {"status": "busy", "passed": False, "changes_category": False}
    name = f"vector-judge-{uuid4().hex}"
    started = time.monotonic()
    output, errors = bytearray(), bytearray()
    overflow = threading.Event()
    process = None
    try:
        workspace = Path(os.getenv("JUDGE_WORKSPACE", "/var/lib/vector-judge/jobs"))
        workspace.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="job-", dir=workspace) as temporary:
            directory = Path(temporary)
            directory.chmod(0o755)
            suffix = "py" if language == "python" else "cjs"
            (directory / f"submission.{suffix}").write_text(source, encoding="utf-8")
            (directory / f"harness.{suffix}").write_text(PYTHON_HARNESS if language == "python" else JS_HARNESS, encoding="utf-8")
            for path in directory.iterdir():
                path.chmod(0o444)
            process = subprocess.Popen(command(name, directory, language), stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            def collect(pipe, target):
                while chunk := pipe.read(4096):
                    if len(target) + len(chunk) > MAX_OUTPUT:
                        overflow.set()
                        process.kill()
                        break
                    target.extend(chunk)

            readers = [threading.Thread(target=collect, args=(pipe, target), daemon=True)
                       for pipe, target in ((process.stdout, output), (process.stderr, errors))]
            for reader in readers:
                reader.start()
            try:
                process.stdin.write(json.dumps(TASKS[task_id]["cases"]).encode())
                process.stdin.close()
                process.wait(timeout=WALL_SECONDS)
                status = "output_limit" if overflow.is_set() else "runtime_error" if process.returncode else "completed"
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
                status = "time_limit"
            except BrokenPipeError:
                status = "runtime_error"
            finally:
                # Removing the named sandbox also stops orphaned child processes.
                subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=8, check=False)
                for reader in readers:
                    reader.join(timeout=2)
            passed_cases = 0
            if status == "completed":
                try:
                    values = [json.loads(line) for line in output.decode().splitlines()]
                    if len(values) != len(TASKS[task_id]["cases"]):
                        status = "invalid_output"
                    else:
                        passed_cases = sum(strict_json_equal(value, expected(task_id, case))
                                           for value, case in zip(values, TASKS[task_id]["cases"]))
                except (ValueError, UnicodeError):
                    status = "invalid_output"
            total = len(TASKS[task_id]["cases"])
            return {"status": status, "passed": status == "completed" and passed_cases == total,
                    "passed_cases": passed_cases, "total_cases": total,
                    "elapsed_ms": round((time.monotonic() - started) * 1000), "changes_category": False,
                    "isolation": "gvisor_runsc", "checker_version": "original-practice-v1"}
    except (OSError, subprocess.SubprocessError, RuntimeError):
        if process and process.poll() is None:
            process.kill()
        return {"status": "infrastructure_error", "passed": False, "changes_category": False}
    finally:
        SEMAPHORE.release()

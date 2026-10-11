"""Isolation adapter tests inspect commands and failure paths; no source execution."""
import importlib
import json
from pathlib import Path
import sys
import hashlib
import hmac
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from services.judge import runner
from services.judge.tasks import expected, public_catalog
from services.judge import main


def test_judge_never_available_on_windows(monkeypatch):
    monkeypatch.setattr(runner.sys, "platform", "win32")
    monkeypatch.setattr(runner.subprocess, "Popen", lambda *a, **kw: pytest.fail("Native execution attempted"))
    result = runner.run_submission("merge-ranges-v1", "python", "raise RuntimeError('must not execute')")
    assert result == {"status": "unavailable", "passed": False, "changes_category": False}


def test_sandbox_command_has_every_mandatory_boundary(monkeypatch, tmp_path):
    monkeypatch.setenv("JUDGE_PYTHON_IMAGE", "python@sha256:" + "a" * 64)
    command = runner.command("vector-judge-test", tmp_path, "python")
    for guard in ["--runtime=runsc", "--network=none", "--read-only", "--cap-drop=ALL",
                  "--security-opt=no-new-privileges:true", "--user=65534:65534", "--pids-limit=32",
                  "--memory=256m", "--memory-swap=256m", "--cpus=1", "--pull=never"]:
        assert guard in command
    assert "--privileged" not in command
    assert not any("docker.sock" in part for part in command)
    assert command[-4:] == ["python", "-I", "-B", "/task/harness.py"]


def test_digest_pin_is_required(monkeypatch):
    monkeypatch.setenv("JUDGE_PYTHON_IMAGE", "python:latest")
    with pytest.raises(RuntimeError):
        runner.image_for("python")
    with pytest.raises(ValueError):
        runner.image_for("bash")


def test_public_catalog_never_leaks_hidden_cases():
    catalog = public_catalog()
    assert len(catalog) == 2
    assert "cases" not in json.dumps(catalog)
    assert all(task["changes_category"] is False for task in catalog)


def test_reference_algorithms_edge_cases():
    assert expected("merge-ranges-v1", [[4, 4], [1, 4], [9, 9], [-1, 0]]) == [[-1, 0], [1, 4], [9, 9]]
    assert expected("rolling-count-v1", {"times": [1, 2, 4, 4, 7], "window": 3}) == [1, 2, 2, 3, 1]
    assert not runner.strict_json_equal([[True, 7]], [[1, 7]])
    assert runner.strict_json_equal([[1, 7]], [[1, 7]])


def signed(raw):
    timestamp = str(int(time.time()))
    signature = hmac.new(("s" * 64).encode(), timestamp.encode() + b"." + raw, hashlib.sha256).hexdigest()
    return {"X-Vector-Timestamp": timestamp, "X-Vector-Signature": signature, "Content-Type": "application/json"}


def payload(source="def solve(data): return data"):
    return json.dumps({"id": "11111111-1111-1111-1111-111111111111", "task_id": "merge-ranges-v1", "language": "python", "source": source}).encode()


@pytest.fixture
def judge_client(monkeypatch):
    monkeypatch.setenv("JUDGE_SHARED_SECRET", "s" * 64)
    main.cache.clear()
    return TestClient(main.app)


def test_gateway_rejects_unsigned_invalid_and_oversized_requests(judge_client, monkeypatch):
    monkeypatch.setattr(main, "run_submission", lambda *a: pytest.fail("Unexpected execution"))
    raw = payload()
    assert judge_client.post("/submissions", content=raw).status_code == 401
    raw = b'{"bad":"submission"}'
    assert judge_client.post("/submissions", content=raw, headers=signed(raw)).status_code == 422
    raw = b'x' * 80_001
    assert judge_client.post("/submissions", content=raw, headers=signed(raw)).status_code == 413


def test_gateway_caches_exact_receipt_and_rejects_reused_id(judge_client, monkeypatch):
    calls = []
    def fake(*args):
        calls.append(args)
        return {"status": "completed", "passed": True}
    monkeypatch.setattr(main, "run_submission", fake)
    raw = payload()
    assert judge_client.post("/submissions", content=raw, headers=signed(raw)).json()["passed"] is True
    assert judge_client.post("/submissions", content=raw, headers=signed(raw)).json()["passed"] is True
    assert len(calls) == 1
    raw = payload("different source")
    assert judge_client.post("/submissions", content=raw, headers=signed(raw)).status_code == 409


def test_gateway_reserves_id_before_execution(judge_client, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    calls = []
    def fake(*args):
        calls.append(args)
        entered.set()
        assert release.wait(timeout=5)
        return {"status": "completed", "passed": True}
    monkeypatch.setattr(main, "run_submission", fake)
    raw = payload()
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(judge_client.post, "/submissions", content=raw, headers=signed(raw))
        assert entered.wait(timeout=3)
        assert judge_client.post("/submissions", content=raw, headers=signed(raw)).status_code == 409
        changed = payload("different concurrent source")
        assert judge_client.post("/submissions", content=changed, headers=signed(changed)).status_code == 409
        release.set()
        assert first.result(timeout=3).status_code == 200
    assert len(calls) == 1

"""Evidence must fail visibly when absent, changed, stale or malformed."""
import hashlib
import json
import shutil
from pathlib import Path

import pytest
from app import evaluation_summary as evidence
from test_domain_api import database, logged


@pytest.fixture()
def snapshot(tmp_path):
    latest = json.loads((evidence.ROOT / evidence.ARTIFACTS[0]).read_text("utf-8"))
    names = {"evaluation/quality-snapshot.json", *evidence.ARTIFACTS}
    for group in ("source_sha256", "evaluation_source_sha256", "dataset_sha256"):
        names.update(latest["versions"][group])
    for name in names:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(evidence.ROOT / name, target)
    return tmp_path


def assert_no_metrics(result, status):
    assert result["status"] == status
    assert result["measurements"] is None
    assert result["human_validity"] == "not_measured"
    assert result["provenance"]["status"] == "unavailable"


def reseal_report(root, report):
    target = root / evidence.ARTIFACTS[0]
    target.write_text(json.dumps(report) + "\n", encoding="utf-8")
    path = root / "evaluation/quality-snapshot.json"
    manifest = json.loads(path.read_text("utf-8"))
    manifest["artifacts"][evidence.ARTIFACTS[0]] = hashlib.sha256(target.read_bytes()).hexdigest()
    path.write_text(json.dumps(manifest), encoding="utf-8")


def test_real_snapshot_preserves_adverse_results_and_holdout_recall(snapshot):
    result = evidence.evaluation_summary(snapshot)
    assert result["status"] == "ready"
    measured = result["measurements"]
    assert measured["retest"]["agreement"] == 0.860417
    assert measured["retest"]["attention_agreement"] == 0.566667
    assert measured["retest"]["negative_item_rest"] == 49
    assert measured["retest"]["undefined_correlations"] == 7
    assert measured["matching_holdout"]["retrieval_recall"] == 0.5889
    assert measured["matching_holdout"]["baselines"]["keyword_all"]["precision5"] == 0.74
    assert result["provenance"]["checked_files"] == 33


def test_missing_evidence_never_invents_zero_performance(tmp_path):
    assert_no_metrics(evidence.evaluation_summary(tmp_path), "unavailable")


def test_modified_report_is_not_presented_as_verified(snapshot):
    path = snapshot / evidence.ARTIFACTS[0]
    path.write_bytes(path.read_bytes() + b" ")
    assert_no_metrics(evidence.evaluation_summary(snapshot), "integrity_mismatch")


def test_new_engine_source_invalidates_historical_current_claim(snapshot):
    path = snapshot / "services/api/app/engines/matching.py"
    path.write_bytes(path.read_bytes() + b"\n# changed after experiment\n")
    assert_no_metrics(evidence.evaluation_summary(snapshot), "source_mismatch")


def test_modified_observations_are_not_hidden_by_unchanged_headline(snapshot):
    path = snapshot / "data/evaluation/assessment-stability-observations.json"
    path.write_bytes(b'{}')
    assert_no_metrics(evidence.evaluation_summary(snapshot), "source_mismatch")


def test_out_of_range_metric_rejected_even_if_artifact_resealed(snapshot):
    report = json.loads((snapshot / evidence.ARTIFACTS[0]).read_text("utf-8"))
    report["matching_holdout"]["baselines"]["full_neutral"]["precision5"]["mean"] = 1.5
    reseal_report(snapshot, report)
    assert_no_metrics(evidence.evaluation_summary(snapshot), "invalid_artifact")


def test_inconsistent_stability_summaries_rejected(snapshot):
    report = json.loads((snapshot / evidence.ARTIFACTS[0]).read_text("utf-8"))
    report["assessment_stability"]["overall"]["agreement"] = 1.0
    reseal_report(snapshot, report)
    assert_no_metrics(evidence.evaluation_summary(snapshot), "invalid_artifact")


def test_source_manifest_cannot_read_outside_workspace(snapshot):
    report = json.loads((snapshot / evidence.ARTIFACTS[0]).read_text("utf-8"))
    report["versions"]["source_sha256"] = {"services/api/app/engines/../../../../outside": "0" * 64}
    reseal_report(snapshot, report)
    assert_no_metrics(evidence.evaluation_summary(snapshot), "invalid_artifact")


def test_report_read_has_a_fixed_byte_limit(snapshot, monkeypatch):
    monkeypatch.setattr(evidence, "MAX_FILE", 1024)
    assert_no_metrics(evidence.evaluation_summary(snapshot), "invalid_artifact")


def test_huge_integer_count_fails_closed_without_float_overflow(snapshot):
    report = json.loads((snapshot / evidence.ARTIFACTS[0]).read_text("utf-8"))
    report["assessment"]["forms"] = 10 ** 400
    reseal_report(snapshot, report)
    assert_no_metrics(evidence.evaluation_summary(snapshot), "invalid_artifact")


def test_incomplete_source_map_cannot_conceal_changed_matcher(snapshot):
    report = json.loads((snapshot / evidence.ARTIFACTS[0]).read_text("utf-8"))
    report["versions"]["source_sha256"].pop("services/api/app/engines/matching.py")
    reseal_report(snapshot, report)
    (snapshot / "services/api/app/engines/matching.py").write_text("changed", encoding="utf-8")
    assert_no_metrics(evidence.evaluation_summary(snapshot), "source_mismatch")


@pytest.mark.parametrize("timestamp", ["not-a-date", "2026-10-07T18:23:00", "x" * 81])
def test_invalid_timestamp_cannot_break_response_contract(snapshot, timestamp):
    report = json.loads((snapshot / evidence.ARTIFACTS[0]).read_text("utf-8"))
    report["generated_at"] = timestamp
    reseal_report(snapshot, report)
    manifest_path = snapshot / "evaluation/quality-snapshot.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    manifest["generated_at"] = timestamp
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    result = evidence.evaluation_summary(snapshot)
    assert_no_metrics(result, "invalid_artifact")
    from app.contracts import EvaluationSummary
    EvaluationSummary.model_validate(result)


def test_sealer_rejects_incomplete_provenance_without_overwriting_manifest(snapshot, monkeypatch):
    from scripts import seal_evaluation
    monkeypatch.setattr(seal_evaluation, "ROOT", snapshot)
    target = snapshot / "evaluation/quality-snapshot.json"
    before = target.read_bytes()
    report_path = snapshot / evidence.ARTIFACTS[0]
    report = json.loads(report_path.read_text("utf-8"))
    report["versions"]["source_sha256"].pop("services/api/app/engines/matching.py")
    report_path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(SystemExit, match="source_mismatch"):
        seal_evaluation.main()
    assert target.read_bytes() == before


def test_real_quality_endpoint_uses_evidence_and_requires_processing(database, monkeypatch, tmp_path):
    monkeypatch.setattr(evidence, "ROOT", tmp_path)
    client = logged()
    response = client.get("/api/v1/quality/summary")
    assert response.status_code == 200
    assert_no_metrics(response.json()["evaluation"], "unavailable")
    from app.contracts import QualitySummary
    QualitySummary.model_validate(response.json())
    assert response.json()["human_pilot"] == {"status": "not_measured", "sample_size": 0}
    assert client.post("/api/v1/auth/consents", json={"consent_processing": False}).status_code == 200
    assert client.get("/api/v1/quality/summary").status_code == 403

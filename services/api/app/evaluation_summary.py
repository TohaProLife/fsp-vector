"""Bounded, read-only projection of measured synthetic artifacts with provenance.

Hashes verify local snapshot integrity, not scientific validity or external review.
Missing, altered or stale evidence never falls back to invented performance numbers.
"""
import hashlib
import json
import math
from datetime import datetime
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[3]
ARTIFACTS = ("evaluation/reports/latest.json", "evaluation/reports/assessment-stability.json",
             "evaluation/ASSESSMENT-STABILITY-PROTOCOL.md")
MAX_FILE = 8 * 1024 * 1024
MAX_TOTAL = 32 * 1024 * 1024
MAX_SOURCES = 128


class InvalidEvidence(ValueError):
    pass


def _number(value, *, integer=False, minimum=0, maximum=None):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or (isinstance(value, float) and not math.isfinite(value))):
        raise InvalidEvidence("invalid_number")
    if integer and not isinstance(value, int):
        raise InvalidEvidence("invalid_count")
    if value < minimum or (maximum is not None and value > maximum):
        raise InvalidEvidence("number_out_of_bounds")
    return value


def _ratio(value):
    return _number(value, maximum=1)


def _count(value):
    return _number(value, integer=True, maximum=1_000_000_000)


def _json(content):
    def forbidden(value):
        raise InvalidEvidence("nonfinite_json")
    result = json.loads(content, parse_constant=forbidden)
    if not isinstance(result, dict):
        raise InvalidEvidence("object_required")
    return result


def evaluation_summary(root=None, *, snapshot=None):
    root = Path(root or ROOT).resolve()
    base = {"status": "unavailable", "reason": "missing_artifact", "synthetic": True,
            "human_validity": "not_measured", "generated_at": None,
            "provenance": {"status": "unavailable", "checked_files": 0,
                           "report_sha256": None, "stability_sha256": None},
            "measurements": None,
            "notice": "Это авторский синтетический эксперимент. Проверка SHA подтверждает целостность снимка, а не человеческую валидность или качество найма."}
    used = 0

    def read(name):
        nonlocal used
        if not isinstance(name, str) or "\\" in name:
            raise InvalidEvidence("unsafe_path")
        pure = PurePosixPath(name)
        if pure.is_absolute() or ".." in pure.parts or ":" in name:
            raise InvalidEvidence("unsafe_path")
        path = (root / name).resolve()
        if not path.is_relative_to(root):
            raise InvalidEvidence("unsafe_path")
        with path.open("rb") as stream:
            content = stream.read(MAX_FILE + 1)
        used += len(content)
        if len(content) > MAX_FILE or used > MAX_TOTAL:
            raise InvalidEvidence("artifact_limit")
        return content

    def check(name, expected):
        if not isinstance(expected, str) or len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
            raise InvalidEvidence("invalid_hash")
        content = read(name)
        if hashlib.sha256(content).hexdigest() != expected:
            return None
        base["provenance"]["checked_files"] += 1
        return content

    try:
        manifest = snapshot if snapshot is not None else _json(read("evaluation/quality-snapshot.json"))
        if (manifest["version"] != "vector-evaluation-snapshot-1" or set(manifest["artifacts"]) != set(ARTIFACTS)
                or manifest["synthetic"] is not True or manifest["human_validity"] != "not_measured"):
            raise InvalidEvidence("unknown_manifest")
        documents = {}
        for name in ARTIFACTS:
            content = check(name, manifest["artifacts"][name])
            if content is None:
                base.update(status="integrity_mismatch", reason="artifact_hash_changed")
                return base
            documents[name] = content
        latest = _json(documents[ARTIFACTS[0]])
        stability = _json(documents[ARTIFACTS[1]])["summary"]
        if latest["assessment_stability"] != stability or stability["protocol_sha256"] != manifest["artifacts"][ARTIFACTS[2]]:
            raise InvalidEvidence("inconsistent_reports")
        timestamp = latest["generated_at"]
        if not isinstance(timestamp, str) or not 10 <= len(timestamp) <= 80:
            raise InvalidEvidence("invalid_timestamp")
        parsed = datetime.fromisoformat(timestamp)
        if parsed.tzinfo is None or parsed.utcoffset() is None or manifest["generated_at"] != timestamp:
            raise InvalidEvidence("timestamp_requires_timezone")
        base["generated_at"] = timestamp
        base["provenance"].update(report_sha256=manifest["artifacts"][ARTIFACTS[0]],
                                  stability_sha256=manifest["artifacts"][ARTIFACTS[1]])
        paths = set()
        groups = (("source_sha256", "services/api/app/engines/"),
                  ("evaluation_source_sha256", "evaluation/"), ("dataset_sha256", "data/evaluation/"))
        for group, prefix in groups:
            sources = latest["versions"][group]
            if not isinstance(sources, dict) or not sources:
                raise InvalidEvidence("missing_source_provenance")
            for name, expected in sources.items():
                if not name.startswith(prefix) or name in paths or len(paths) >= MAX_SOURCES:
                    raise InvalidEvidence("unsafe_source_provenance")
                paths.add(name)
                if check(name, expected) is None:
                    base.update(status="source_mismatch", reason="source_or_data_changed")
                    return base
            pattern = "*" if group == "dataset_sha256" else "*.py"
            current_paths = {(prefix + path.name) for path in (root / prefix).glob(pattern) if path.is_file()}
            if set(sources) != current_paths:
                base.update(status="source_mismatch", reason="incomplete_source_provenance")
                return base
        observation = "data/evaluation/assessment-stability-observations.json"
        if latest["versions"]["dataset_sha256"][observation] != stability["observations_sha256"]:
            raise InvalidEvidence("observations_disagree")
        bank = latest["assessment"]
        holdout = latest["matching_holdout"]
        if (holdout["split"] != "locked_seed_holdout" or _count(holdout["human_labelers"]) != 0
                or holdout["labels_kind"] != "PROGRAMMATIC_SYNTHETIC_LATENT_RUBRIC"
                or not isinstance(bank["failures"], list)):
            raise InvalidEvidence("unsupported_population")
        full = holdout["baselines"]["full_neutral"]
        baselines = {name: {"precision5": _ratio(holdout["baselines"][name]["precision5"]["mean"]),
                            "ndcg10_end_to_end": _ratio(holdout["baselines"][name]["ndcg10_end_to_end"]["mean"])}
                     for name in ("random_eligible", "keyword_all", "strong_category_test", "full_neutral")}
        measurements = {
            "bank": {"forms": _count(bank["forms"]), "items": _count(bank["items_checked"]),
                     "failures": _count(len(bank["failures"])), "families": _count(bank["distinct_families_exercised"])},
            "retest": {"protocol_id": stability["protocol_id"], "pairs": _count(stability["overall"]["pairs"]),
                       "forms": _count(stability["distinct_forms"]),
                       "administrations": _count(stability["profile_attempt_administrations"]),
                       "agreement": _ratio(stability["overall"]["agreement"]),
                       "attention_agreement": _ratio(stability["by_kind"]["attention_boundary"]["agreement"]),
                       "negative_item_rest": _count(stability["item_flags"].get("negative_corrected_correlation", 0)),
                       "nonpositive_separation": _count(stability["item_flags"].get("nonpositive_upper_lower_separation", 0)),
                       "undefined_correlations": _count(stability["undefined_item_rest_correlations"]),
                       "nonmonotonic_flags": _count(stability["nonmonotonic_grade_profile_comparisons"])},
            "matching_holdout": {"queries": _count(holdout["needs"]), "labels": _count(holdout["labels"]),
                                 "precision5": _ratio(full["precision5"]["mean"]),
                                 "ndcg10_end_to_end": _ratio(full["ndcg10_end_to_end"]["mean"]),
                                 "ndcg10_eligible": _ratio(full["ndcg10_eligible"]["mean"]),
                                 "retrieval_recall": _ratio(holdout["retrieval_recall_mean"]),
                                 "gate_violations": _count(holdout["gate_violations"]), "baselines": baselines}}
        base.update(status="ready", reason=None, measurements=measurements)
        base["provenance"]["status"] = "verified"
        return base
    except FileNotFoundError:
        return base
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        base.update(status="invalid_artifact", reason="invalid_or_unreadable_evidence")
        return base

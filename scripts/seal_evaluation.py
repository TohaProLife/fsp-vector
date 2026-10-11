"""Pin existing measured artifacts; this command does not run or improve evaluation."""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATHS = ("evaluation/reports/latest.json", "evaluation/reports/assessment-stability.json",
         "evaluation/ASSESSMENT-STABILITY-PROTOCOL.md")


def main():
    artifacts = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in PATHS}
    latest = json.loads((ROOT / PATHS[0]).read_text("utf-8"))
    stability = json.loads((ROOT / PATHS[1]).read_text("utf-8"))["summary"]
    if latest["assessment_stability"] != stability:
        raise SystemExit("Reports disagree; do not seal inconsistent measurements.")
    if stability["protocol_sha256"] != artifacts[PATHS[2]]:
        raise SystemExit("Protocol changed after measurement; keep the historical baseline.")
    snapshot = {"version": "vector-evaluation-snapshot-1", "generated_at": latest["generated_at"],
                "artifacts": artifacts, "synthetic": True, "human_validity": "not_measured"}
    sys.path.insert(0, str(ROOT / "services/api"))
    from app.evaluation_summary import evaluation_summary
    validation = evaluation_summary(ROOT, snapshot=snapshot)
    if validation["status"] != "ready":
        raise SystemExit("Cannot seal stale or invalid measurements: " + validation["status"])
    target = ROOT / "evaluation/quality-snapshot.json"
    target.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"sealed": str(target), "artifacts": len(artifacts), "measurements_recomputed": False}))


if __name__ == "__main__":
    main()

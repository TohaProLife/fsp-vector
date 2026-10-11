"""Export implementation schema without touching accounts or application data."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api"))
from app.main import app

path = ROOT / "docs" / "api" / "openapi.json"
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"Exported {len(app.openapi()['paths'])} API paths to docs/api/openapi.json")

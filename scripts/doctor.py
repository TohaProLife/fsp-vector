"""Report actual local capabilities; never mark an unconfigured judge available."""
import importlib.metadata
import json
import platform
import shutil
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def probe(url):
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            return {"ready": response.status == 200}
    except OSError:
        return {"ready": False}


def main():
    checks = {"os": platform.platform(), "python": sys.version.split()[0], "node": shutil.which("node"),
              "docker": shutil.which("docker"), "runtime_manifest": (ROOT / ".runtime/runtime-manifest.json").exists(),
              "services": {"web": probe("http://127.0.0.1:3000"), "api": probe("http://127.0.0.1:8000/ready"),
                           "identity": probe("http://127.0.0.1:8081/realms/vector/.well-known/openid-configuration")},
              "untrusted_code_execution": "not_enabled_on_windows", "safe_practice": "bounded_data_and_sql"}
    checks["packages"] = {}
    for package in ("fastapi", "sqlalchemy", "psycopg", "pydantic", "PyJWT"):
        try:
            checks["packages"][package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            checks["packages"][package] = "missing"
    print(json.dumps(checks, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

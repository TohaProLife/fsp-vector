"""Install project-scoped, official Windows runtimes without administrator access."""
from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime"
ASSETS = {
    "mailpit-1.31.4.zip": {
        "url": "https://github.com/axllent/mailpit/releases/download/v1.31.4/mailpit-windows-amd64.zip",
        "sha256": "0dd6ec909a6f5b2b66682b22d82abce97ab793e30766bf2f642b691e70a4a16b",
        "source": "https://github.com/axllent/mailpit/releases/tag/v1.31.4",
    },
    "postgresql-18.6.zip": {
        "url": "https://sbp.enterprisedb.com/getfile.jsp?fileid=1260609",
        "sha256": None,
        "source": "https://www.enterprisedb.com/download-postgresql-binaries",
    },
    "keycloak-26.8.0.zip": {
        "url": "https://github.com/keycloak/keycloak/releases/download/26.8.0/keycloak-26.8.0.zip",
        "sha256": "7ed1de3fda2598369262613bf682aab7e233d80a38c405e91588f7a7454370a1",
        "source": "https://www.keycloak.org/downloads",
    },
    "java25.zip": {
        "url": "https://github.com/adoptium/temurin25-binaries/releases/download/jdk-25.0.4.1%2B1/OpenJDK25U-jre_x64_windows_hotspot_25.0.4.1_1.zip",
        "sha256": "4c95451cea98556def2c54f7782933f52a26d4a36bd85e1d59f0364464828b07",
        "source": "https://github.com/adoptium/temurin25-binaries/releases/tag/jdk-25.0.4.1%2B1",
    },
}


def install_asset(name: str, asset: dict) -> dict:
    archive = RUNTIME / "downloads" / name
    archive.parent.mkdir(parents=True, exist_ok=True)
    if not archive.exists():
        request = urllib.request.Request(asset["url"], headers={"User-Agent": "FSP-Vector-Local-Setup"})
        partial = archive.with_suffix(".partial")
        print(f"Downloading {name}", flush=True)
        with urllib.request.urlopen(request, timeout=90) as response, partial.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        partial.replace(archive)
    with archive.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    if asset["sha256"] and digest != asset["sha256"]:
        raise RuntimeError(f"Checksum mismatch for {name}; archive not executed")
    marker = RUNTIME / f"{name}.installed"
    if marker.exists() and marker.read_text(encoding="utf-8") != digest:
        raise RuntimeError(f"Previously installed archive changed: {name}")
    if not marker.exists():
        print(f"Extracting {name}", flush=True)
        with zipfile.ZipFile(archive) as bundle:
            for item in bundle.infolist():
                target = (RUNTIME / item.filename).resolve()
                if not target.is_relative_to(RUNTIME.resolve()):
                    raise RuntimeError("Invalid archive path")
            bundle.extractall(RUNTIME)
        marker.write_text(digest, encoding="utf-8")
    print(f"Ready {name}", flush=True)
    return {"asset": name, "source": asset["source"], "sha256": digest,
            "publisher_digest_verified": bool(asset["sha256"]), "bytes": archive.stat().st_size}


def main() -> None:
    if os.name != "nt":
        raise SystemExit("Use system PostgreSQL/Java or deploy/compose.yaml on Linux.")
    RUNTIME.mkdir(exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(install_asset, name, asset) for name, asset in ASSETS.items()]
        manifest = [future.result() for future in futures]
    (RUNTIME / "runtime-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

"""Read official registry manifests and pin deployment images; never pull/run images."""
import concurrent.futures
import json
import re
from pathlib import Path
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
IMAGES = {"python": ("library/python", "3.14.6-slim-bookworm"),
          "node": ("library/node", "24.16.0-bookworm-slim"),
          "postgres": ("library/postgres", "18.6-bookworm"),
          "mailpit": ("axllent/mailpit", "v1.31.4")}


def resolve(entry):
    key, (repository, tag) = entry
    url = "https://auth.docker.io/token?" + urllib.parse.urlencode({"service": "registry.docker.io", "scope": f"repository:{repository}:pull"})
    token = json.loads(urllib.request.urlopen(url, timeout=15).read())["token"]
    request = urllib.request.Request(f"https://registry-1.docker.io/v2/{repository}/manifests/{tag}", method="HEAD",
        headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json"})
    with urllib.request.urlopen(request, timeout=15) as response:
        digest = response.headers["Docker-Content-Digest"]
    assert digest.startswith("sha256:") and len(digest) == 71
    name = repository.removeprefix("library/")
    return key, {"tag": f"{name}:{tag}", "pinned": f"{name}:{tag}@{digest}", "source": "official_distribution_registry"}


if __name__ == "__main__":
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        values = dict(executor.map(resolve, IMAGES.items()))
    lock_path = ROOT / "deploy/image-lock.json"
    # Keep manifests obtained from other registries. This command refreshes
    # Docker Hub entries only; it must not erase the separately verified Quay pin.
    previous = json.loads(lock_path.read_text(encoding="utf-8")) if lock_path.exists() else {}
    previous.update(values)
    lock_path.write_text(json.dumps(previous, indent=2) + "\n", encoding="utf-8")
    for file, key in [("deploy/Dockerfile.api", "python"), ("deploy/Dockerfile.web", "node")]:
        path = ROOT / file
        content = path.read_text(encoding="utf-8")
        content = re.sub(re.escape(values[key]["tag"]) + r"(?:@sha256:[a-f0-9]{64})?", values[key]["pinned"], content)
        path.write_text(content, encoding="utf-8")
    path = ROOT / "deploy/compose.local.yml"
    content = path.read_text(encoding="utf-8")
    for key in ("postgres", "mailpit"):
        content = re.sub(re.escape(values[key]["tag"]) + r"(?:@sha256:[a-f0-9]{64})?", values[key]["pinned"], content)
    path.write_text(content, encoding="utf-8")
    print("Four registry tags verified and pinned; no image downloaded or container run.")

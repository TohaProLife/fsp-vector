"""Generate private local Docker credentials and an import realm, never overwrite."""
import json
from pathlib import Path
import secrets

root = Path(__file__).resolve().parents[1]
directory = root / ".local" / "compose"
directory.mkdir(parents=True, exist_ok=True)
env_file = directory / "compose.env"
if not env_file.exists():
    names = ["PG_ADMIN_PASSWORD", "PG_APP_PASSWORD", "PG_IDENTITY_PASSWORD", "KEYCLOAK_ADMIN_PASSWORD", "OIDC_CLIENT_SECRET", "ATS_WEBHOOK_SECRET"]
    env_file.write_text("\n".join(f"{key}={secrets.token_hex(32)}" for key in names) + "\n", encoding="utf-8")
    env_file.chmod(0o600)
values = dict(line.split("=", 1) for line in env_file.read_text(encoding="utf-8").splitlines() if "=" in line)
template = json.loads((root / "deploy/keycloak/vector-realm.template.json").read_text(encoding="utf-8").replace("__CLIENT_SECRET__", values["OIDC_CLIENT_SECRET"]))
template["smtpServer"]["host"] = "mailpit"
template["clients"][0]["attributes"]["backchannel.logout.url"] = "http://api:8000/api/v1/auth/oidc/backchannel-logout"
(directory / "vector-realm.json").write_text(json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8")
print("Private Docker configuration prepared in .local/compose. No containers started.")

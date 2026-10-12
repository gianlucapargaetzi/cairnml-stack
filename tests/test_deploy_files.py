import re
from pathlib import Path

import yaml
from mlops_agent.config import AgentSettings
from mlops_server.settings import Settings

DEPLOY = Path(__file__).resolve().parents[1] / "deploy"
ROLES = ("idp", "nas", "server", "agent")


def _compose(role):
    return yaml.safe_load((DEPLOY / role / "compose.yaml").read_text())


def _env_keys(compose, prefix):
    keys = set()
    for service in compose["services"].values():
        env = service.get("environment") or {}
        names = env.keys() if isinstance(env, dict) else [e.split("=")[0] for e in env]
        keys |= {n for n in names if n.startswith(prefix)}
    return keys


def test_server_environment_names_match_settings_fields():
    fields = set(Settings.model_fields)
    for key in _env_keys(_compose("server"), "MLOPS_"):
        assert key.removeprefix("MLOPS_").lower() in fields, key


def test_agent_environment_names_match_settings_fields():
    fields = set(AgentSettings.model_fields)
    for key in _env_keys(_compose("agent"), "MLOPS_AGENT_"):
        assert key.removeprefix("MLOPS_AGENT_").lower() in fields, key


def test_every_stack_joins_the_shared_external_network():
    for role in ROLES:
        compose = _compose(role)
        assert compose["networks"]["mlops"] == {"name": "mlops", "external": True}, role
        for name, service in compose["services"].items():
            assert "mlops" in service["networks"], f"{role}/{name}"


def test_all_in_one_file_includes_every_stack():
    root = yaml.safe_load((DEPLOY / "compose.yaml").read_text())
    included = {
        Path(item["path"] if isinstance(item, dict) else item).parent.name
        for item in root["include"]
    }
    assert included == set(ROLES)


def test_public_urls_use_role_hostnames_not_localhost():
    env = (DEPLOY / ".env.example").read_text()
    for line in env.splitlines():
        if re.match(r"^(MLOPS_SERVER_URL|MLOPS_IDP_ISSUER|MLOPS_NAS_URL)=", line):
            assert "localhost" not in line and "127.0.0.1" not in line, line
            assert re.search(r"://mlops-(server|idp|nas)[:/]", line), line


def test_realm_has_device_flow_client_and_admin_role():
    import json

    realm = json.loads((DEPLOY / "idp" / "realm-mlops.json").read_text())
    client = next(c for c in realm["clients"] if c["clientId"] == "mlops-cli")
    assert (
        client["publicClient"] is True
        and client["attributes"]["oauth2.device.authorization.grant.enabled"] == "true"
    )
    assert any(r["name"] == "mlops-admin" for r in realm["roles"]["realm"])
    admin = next(u for u in realm["users"] if u["username"] == "admin")
    assert "mlops-admin" in admin["realmRoles"]

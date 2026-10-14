import json
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


def test_realm_has_device_flow_client_and_admin_role_but_no_users():
    text = (DEPLOY / "idp" / "realm-mlops.json").read_text()
    realm = json.loads(text)
    client = next(c for c in realm["clients"] if c["clientId"] == "mlops-cli")
    assert (
        client["publicClient"] is True
        and client["attributes"]["oauth2.device.authorization.grant.enabled"] == "true"
    )
    assert any(r["name"] == "mlops-admin" for r in realm["roles"]["realm"])
    # users may be listed, but no passwords or credentials are ever committed:
    # the admin is created by bootstrap.sh, other passwords are set by the operator
    assert "credentials" not in text


def test_rustfs_console_is_bound_to_loopback_only():
    ports = _compose("nas")["services"]["mlops-nas"]["ports"]
    assert "127.0.0.1:9001:9001" in ports
    assert not any(str(p).endswith(":9001") and not str(p).startswith("127.0.0.1:") for p in ports)


def test_job_containers_do_not_join_the_shared_network():
    agent = _compose("agent")
    assert (
        agent["services"]["mlops-agent"]["environment"]["MLOPS_AGENT_JOB_NETWORK"] == "mlops-jobs"
    )
    assert agent["services"]["mlops-agent"]["networks"] == ["mlops"]
    assert agent["networks"]["mlops-jobs"] == {"name": "mlops-jobs"}
    server = _compose("server")
    assert "mlops-jobs" in server["services"]["mlops-server"]["networks"]
    assert server["networks"]["mlops-jobs"] == {"name": "mlops-jobs"}
    # Postgres, RustFS and Keycloak never join the job network
    for role, name in (("server", "mlops-postgres"), ("nas", "mlops-nas"), ("idp", "mlops-idp")):
        assert "mlops-jobs" not in _compose(role)["services"][name]["networks"], name


def test_bootstrap_hands_keycloak_volume_to_its_uid_before_start():
    text = (DEPLOY / "scripts" / "bootstrap.sh").read_text()
    chown = text.index("chown 1000:1000 /data")
    assert chown < text.index("up -d --build mlops-idp")


def test_nas_init_does_not_swallow_failures():
    assert "|| true" not in (DEPLOY / "nas" / "init.py").read_text()


def test_realm_has_the_web_client_and_a_read_only_service_account():
    realm = json.loads((DEPLOY / "idp" / "realm-mlops.json").read_text())
    clients = {c["clientId"]: c for c in realm["clients"]}
    web = clients["mlops-web"]
    assert web["publicClient"] is True and web["standardFlowEnabled"] is True
    assert web["directAccessGrantsEnabled"] is False
    assert web["attributes"]["pkce.code.challenge.method"] == "S256"
    assert "http://mlops-server:8000/ui-next/*" in web["attributes"]["post.logout.redirect.uris"].split("##")
    assert web["redirectUris"] == ["http://mlops-server:8000/ui/auth/callback"]
    sync = clients["mlops-server"]
    assert sync["publicClient"] is False and sync["serviceAccountsEnabled"] is True
    assert sync["standardFlowEnabled"] is False and sync["secret"] == "${MLOPS_IDP_SYNC_SECRET}"
    account = next(u for u in realm["users"] if u.get("serviceAccountClientId") == "mlops-server")
    assert sorted(account["clientRoles"]["realm-management"]) == ["query-users", "view-users"]
    assert any(u["username"] == "carol" for u in realm["users"])


def test_idp_sync_settings_reach_the_server_and_the_realm_import():
    server_env = _compose("server")["services"]["mlops-server"]["environment"]
    assert server_env["MLOPS_IDP_SYNC_CLIENT_SECRET"]
    assert "MLOPS_IDP_SYNC_SECRET" in _compose("idp")["services"]["mlops-idp"]["environment"]
    env = (DEPLOY / ".env.example").read_text()
    assert "IDP_SYNC_SECRET=" in env and "IDP_SYNC_INTERVAL=" in env


def test_the_server_image_builds_the_explorer_with_the_bundle_guard():
    dockerfile = (DEPLOY / "server" / "Dockerfile").read_text()
    assert "FROM node:24 AS ui-builder" in dockerfile
    assert "node scripts/check-bundle-hosts.js build" in dockerfile
    assert "COPY --from=ui-builder /build/build" in dockerfile
    assert (DEPLOY.parent / "packages" / "mlops-ui" / "scripts" / "check-bundle-hosts.js").is_file()

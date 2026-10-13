"""End-to-end fixtures. They talk to the real compose stack and never mock authentication.

Environment:
  MLOPS_E2E=1                   enable the suite (without it every e2e test skips)
  MLOPS_E2E_SERVER              server URL (default http://mlops-server:8000)
  MLOPS_E2E_ISSUER              Keycloak realm URL (default http://mlops-idp:8180/realms/mlops)
  MLOPS_E2E_PASSWORD_<USER>     password of the realm user <USER> (ADMIN, DEV, EVE, CAROL).
                                No password is stored in the repository. A test whose user has
                                no password here is skipped.
  MLOPS_E2E_GITHUB_REPO         owner/name; with MLOPS_E2E_GITHUB_REPO_URL it enables
                                test_reproduce.py (see docs/e2e-test-repo.md)

The Keycloak master admin password (KC_ADMIN_PASSWORD) is read from deploy/.env, which is
git-ignored. Admin actions go through the real HTTP admin endpoints with the admin's enrolled key;
the `mlops` CLI has no `admin` subcommands.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "deploy"
SERVER = os.environ.get("MLOPS_E2E_SERVER", "http://mlops-server:8000")
ISSUER = os.environ.get("MLOPS_E2E_ISSUER", "http://mlops-idp:8180/realms/mlops")
KEYCLOAK = ISSUER.split("/realms/")[0]
MLOPS_BIN = str(Path(sys.executable).parent / "mlops")
PROJECT = "e2e/demo"


def dotenv() -> dict[str, str]:
    values = {}
    for line in (DEPLOY / ".env").read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            values[key] = value
    return values


def _wait_for(fn, timeout: float = 120.0, interval: float = 2.0, message: str = "condition"):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        try:
            result = fn()
            if result:
                return result
        except Exception as exc:  # keep polling
            last = exc
        time.sleep(interval)
    raise AssertionError(f"timed out waiting for {message} (last error: {last})")


def user_password(username: str) -> str:
    variable = f"MLOPS_E2E_PASSWORD_{username.upper()}"
    value = os.environ.get(variable)
    if not value:
        pytest.skip(f"set {variable} to the password of the Keycloak user {username!r}")
    return value


def idp_token(username: str) -> str:
    """A real Keycloak token through the password grant (test-only, see direct_grants)."""
    response = httpx.post(
        f"{ISSUER}/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": "mlops-cli",
            "username": username,
            "password": user_password(username),
        },
    )
    response.raise_for_status()
    return response.json()["access_token"]


@pytest.fixture(scope="session")
def wait_for():
    return _wait_for


@pytest.fixture(scope="session")
def server_url():
    return SERVER


@pytest.fixture(scope="session")
def stack():
    if not os.environ.get("MLOPS_E2E"):
        pytest.skip("set MLOPS_E2E=1 with the compose stack running (deploy/scripts/bootstrap.sh)")
    if not (DEPLOY / ".env").exists():
        pytest.skip("deploy/.env is missing: run deploy/scripts/bootstrap.sh first")
    try:
        httpx.get(f"{SERVER}/api/v1/healthz", timeout=5).raise_for_status()
    except Exception as exc:
        pytest.skip(f"stack not reachable at {SERVER}: {exc}")
    return dotenv()


@pytest.fixture(scope="session")
def direct_grants(stack):
    """Let the test log in with a password. The server still verifies the real Keycloak token.

    Enables directAccessGrantsEnabled on the mlops-cli client and restores it at teardown.
    """
    admin = httpx.post(
        f"{KEYCLOAK}/realms/master/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": stack.get("KC_ADMIN", "kcadmin"),
            "password": stack["KC_ADMIN_PASSWORD"],
        },
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {admin}"}
    url = f"{KEYCLOAK}/admin/realms/mlops/clients"
    client = httpx.get(url, params={"clientId": "mlops-cli"}, headers=headers).json()[0]
    client["directAccessGrantsEnabled"] = True
    httpx.put(f"{url}/{client['id']}", json=client, headers=headers).raise_for_status()
    yield
    client["directAccessGrantsEnabled"] = False
    httpx.put(f"{url}/{client['id']}", json=client, headers=headers).raise_for_status()


class Cli:
    """One enrolled client of a Keycloak user, with its own config and data directory."""

    def __init__(self, directory: Path, username: str) -> None:
        self.directory, self.username = directory, username
        self.env = {
            **os.environ,
            "MLOPS_CONFIG_DIR": str(directory / "cfg"),
            "MLOPS_DATA_DIR": str(directory / "data"),
        }
        self._api = None

    def run(
        self, *args: str, check: bool = True, cwd: Path | None = None, input: str | None = None
    ):
        result = subprocess.run(
            [MLOPS_BIN, *args],
            env=self.env,
            capture_output=True,
            text=True,
            cwd=cwd,
            input=input,
            timeout=300,
        )
        if check and result.returncode != 0:
            raise AssertionError(
                f"mlops {' '.join(args)} failed:\n{result.stdout}\n{result.stderr}"
            )
        return result

    def python(self, script: Path, *args: str, cwd: Path | None = None):
        return subprocess.run(
            [sys.executable, str(script), *args],
            env=self.env,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=600,
        )

    def enroll(self) -> None:
        self.run(
            "enroll", "--server", SERVER, "--idp-token", idp_token(self.username), "--name", "e2e"
        )

    def api(self):
        """An ApiClient that uses this client's enrolled key (real HTTP)."""
        from mlops.api import ApiClient

        if self._api is None:
            old = {k: os.environ.get(k) for k in ("MLOPS_CONFIG_DIR", "MLOPS_DATA_DIR")}
            os.environ.update(
                MLOPS_CONFIG_DIR=self.env["MLOPS_CONFIG_DIR"],
                MLOPS_DATA_DIR=self.env["MLOPS_DATA_DIR"],
            )
            try:
                self._api = ApiClient.from_config()
            finally:
                for key, value in old.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value
        return self._api


@pytest.fixture(scope="session")
def make_cli(stack, direct_grants, tmp_path_factory):
    def _make(username: str) -> Cli:
        cli = Cli(tmp_path_factory.mktemp(f"cli-{username}"), username)
        cli.enroll()
        return cli

    return _make


@pytest.fixture(scope="session")
def admin(make_cli):
    return make_cli("admin")


@pytest.fixture(scope="session")
def dev(make_cli):
    return make_cli("dev")


@pytest.fixture(scope="session")
def project(admin, dev):
    http = admin.api()._http
    created = http.post("/api/v1/projects", json={"slug": PROJECT, "name": "E2E demo"})
    assert created.status_code in (200, 409), created.text  # 409: left over from an earlier run
    added = http.post("/api/v1/project-members", json={"project": PROJECT, "username": "dev"})
    assert added.status_code == 200, added.text
    return PROJECT


@pytest.fixture(scope="session")
def agent_ready(admin, stack):
    http = admin.api()._http

    def live_agents():
        agents = http.get("/api/v1/admin/agents").json()
        return [a for a in agents if not a["revoked"]]

    def heartbeat_recent():
        for agent in live_agents():
            if not agent["last_seen"]:
                continue
            seen = datetime.fromisoformat(agent["last_seen"])
            if seen.tzinfo is None:
                seen = seen.replace(tzinfo=UTC)
            if datetime.now(UTC) - seen < timedelta(seconds=120):
                return True
        return False

    if not live_agents():
        token = http.post("/api/v1/admin/agent-tokens", json={"queues": ["default"]})
        token.raise_for_status()
        secret = token.json()["token"]
        env_file = DEPLOY / ".env"
        lines = [
            f"MLOPS_AGENT_ENROLL_TOKEN={secret}"
            if line.startswith("MLOPS_AGENT_ENROLL_TOKEN=")
            else line
            for line in env_file.read_text().splitlines()
        ]
        env_file.write_text("\n".join(lines) + "\n")
        subprocess.run(
            ["docker", "compose", "-f", str(DEPLOY / "compose.yaml"), "up", "-d", "mlops-agent"],
            check=True,
            cwd=DEPLOY,
        )
    _wait_for(heartbeat_recent, timeout=180, message="an enrolled agent with a recent heartbeat")
    return True


class KeycloakAdmin:
    """Enables or disables realm users in Keycloak, the way an operator would in the IdP."""

    def __init__(self, headers: dict) -> None:
        self.headers = headers

    def _user_id(self, username: str) -> str:
        users = httpx.get(
            f"{KEYCLOAK}/admin/realms/mlops/users",
            params={"username": username, "exact": "true"},
            headers=self.headers,
        ).json()
        return users[0]["id"]

    def set_enabled(self, username: str, enabled: bool) -> None:
        user_id = self._user_id(username)
        body = httpx.get(
            f"{KEYCLOAK}/admin/realms/mlops/users/{user_id}", headers=self.headers
        ).json()
        body["enabled"] = enabled
        httpx.put(
            f"{KEYCLOAK}/admin/realms/mlops/users/{user_id}", json=body, headers=self.headers
        ).raise_for_status()


@pytest.fixture(scope="session")
def keycloak_admin(stack):
    token = httpx.post(
        f"{KEYCLOAK}/realms/master/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": stack.get("KC_ADMIN", "kcadmin"),
            "password": stack["KC_ADMIN_PASSWORD"],
        },
    ).json()["access_token"]
    return KeycloakAdmin({"Authorization": f"Bearer {token}"})


@pytest.fixture(scope="session")
def password_for():
    """Password lookup for browser logins (MLOPS_E2E_PASSWORD_<USER>); no literal in the repo."""
    return user_password


@pytest.fixture
def login(password_for):
    """Logs a realm user in through the IdP login page. The password comes from the environment."""
    from playwright.sync_api import expect  # noqa: PLC0415  (the ui group is optional)

    ui_base = SERVER.rstrip("/") + "/ui-next/"

    def _login(page, username="dev"):
        password = password_for(username)
        page.goto(ui_base)
        page.wait_for_url(re.compile(r"/realms/mlops/"))
        page.fill("#username", username)
        page.fill("#password", password)
        page.click("#kc-login")
        page.wait_for_url(re.compile(r"/ui-next/"))
        expect(page.locator("#user")).to_have_text(username)

    return _login


@pytest.fixture(scope="session")
def dispatch_image():
    """Returns dispatch_image(dev, command, name, queue="default"). It dispatches a one-command
    image job through the real CLI and returns the job id."""

    def _dispatch(dev, command, name, queue="default"):
        folder = dev.directory / "specs"
        folder.mkdir(exist_ok=True)
        spec = folder / f"{name}.yaml"
        spec.write_text(
            f"name: {name}\nproject: {PROJECT}\nqueue: {queue}\nexperiment: testing\n"
            "runtime:\n  type: image\n  image: alpine:3.20\n  entrypoint: [/bin/sh, -c]\n"
            f"  command: ['{command}']\nresources: {{cpu: 1, memory_gb: 0.5}}\n"
            "params: {lr: 0.1}\n"
        )
        out = dev.run("dispatch", "--file", str(spec)).stdout
        return next(w for w in out.split() if w.startswith("job_"))

    return _dispatch

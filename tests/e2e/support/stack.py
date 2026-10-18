"""The suite's own stack: started for each test session, and removed at its end.

The stack is a separate compose project (tests/e2e/stack/compose.yaml) with:
- its own state folder (data, secrets, the realm copy), created in a temporary directory;
- its own accounts: the admin's password is generated for the session;
- its own ports, on this machine's network address (found from the default route), so nothing needs /etc/hosts
  and nothing is shared with the stack under deploy/.

Only the Docker daemon and the image cache are shared with the rest of the machine. The clearml-server image is
the one the deploy/ stack builds; the suite does not change it.
"""

import json
import os
import random
import secrets
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path

import requests

from . import settings

PROJECT_PREFIX = "mlops-e2e"
COMPOSE_FILE = Path(__file__).resolve().parents[1] / "stack" / "compose.yaml"
REALM_TEMPLATE = Path(__file__).resolve().parents[3] / "deploy" / "idp" / "realm-mlops.json"
STORAGE_SCRIPT = Path(__file__).resolve().parents[3] / "deploy" / "storage" / "init.py"
ADMIN_NAME = "e2e-admin"

# Owners of the data folders inside the containers (the same as deploy/scripts/bootstrap.sh).
DATA_OWNERS = {"idp": "1000:1000", "rustfs": "10001:10001", "mongo": "999:999", "redis": "999:999",
               "elastic": "1000:1000"}


class StackError(Exception):
    pass


def host_address() -> str:
    """This machine's address on the default route: reachable from the host and from the containers."""
    if os.environ.get("MLOPS_E2E_HOST"):
        return os.environ["MLOPS_E2E_HOST"]
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.connect(("192.0.2.1", 9))  # no packet is sent; this only selects the route
        return probe.getsockname()[0]


def _port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


def pick_ports(host: str, count: int = 4) -> list:
    chosen = []
    candidates = list(range(18000, 19000))
    random.shuffle(candidates)
    for port in candidates:
        if port in chosen or not _port_free(host, port):
            continue
        chosen.append(port)
        if len(chosen) == count:
            return chosen
    raise StackError("no free ports for the test stack")


class IsolatedStack:
    def __init__(self, keep: bool = False):
        self.keep = keep
        self.host = host_address()
        self.state = Path(tempfile.mkdtemp(prefix="mlops-e2e-stack-"))
        api, web, idp, storage = pick_ports(self.host)
        self.ports = {"api": api, "web": web, "idp": idp, "storage": storage}
        self.admin_password = secrets.token_urlsafe(18)
        self.rustfs_password = secrets.token_urlsafe(18)
        self.s3_access = "e2e-server"
        # One compose project per session, so two sessions never share containers or networks.
        self.project = f"{PROJECT_PREFIX}-{secrets.token_hex(3)}"

    # --- URLs as the suite (and the containers) see them -----------------------------------------------------------

    @property
    def api_url(self) -> str:
        return f"http://{self.host}:{self.ports['api']}"

    @property
    def web_url(self) -> str:
        return f"http://{self.host}:{self.ports['web']}"

    @property
    def idp_url(self) -> str:
        return f"http://{self.host}:{self.ports['idp']}"

    @property
    def storage_url(self) -> str:
        return f"http://{self.host}:{self.ports['storage']}"

    def configure_settings(self) -> None:
        settings.configure(api=self.api_url, web=self.web_url, idp=self.idp_url, storage=self.storage_url,
                           admin_user=ADMIN_NAME, admin_password=self.admin_password, project=self.project)

    # --- files -----------------------------------------------------------------------------------------------------

    def prepare(self) -> None:
        for folder in ("data/idp", "data/rustfs", "data/mongo/db", "data/mongo/configdb", "data/redis",
                       "data/elastic", "data/logs", "secrets"):
            (self.state / folder).mkdir(parents=True, exist_ok=True)
        for name in ("token_secret", "session_secret", "s3_secret_key"):
            path = self.state / "secrets" / name
            path.write_text(secrets.token_urlsafe(48))
            path.chmod(0o600)
        shutil.copy(STORAGE_SCRIPT, self.state / "init.py")
        self._write_realm()
        # The web app's API address: the web server's /api route, so the app never reaches a port of its own guess.
        (self.state / "configs").mkdir(exist_ok=True)
        (self.state / "configs" / "configuration.json").write_text(json.dumps({"apiBaseUrl": "/api"}))

    def _write_realm(self) -> None:
        """The committed realm, with this stack's addresses in place of the deploy/ names."""
        text = REALM_TEMPLATE.read_text()
        text = text.replace("http://mlops-clearml:8008", self.api_url)
        text = text.replace("http://mlops-clearml:8080", self.web_url)
        json.loads(text)  # the result must still be a realm
        (self.state / "realm-mlops.json").write_text(text)

    def _env(self) -> dict:
        return {
            **os.environ,
            "COMPOSE_PROJECT_NAME": self.project,
            "E2E_HOST": self.host,
            "E2E_STATE": str(self.state),
            "E2E_API_PORT": str(self.ports["api"]),
            "E2E_WEB_PORT": str(self.ports["web"]),
            "E2E_IDP_PORT": str(self.ports["idp"]),
            "E2E_STORAGE_PORT": str(self.ports["storage"]),
            "E2E_KC_ADMIN": ADMIN_NAME,
            "E2E_KC_ADMIN_PASSWORD": self.admin_password,
            "E2E_RUSTFS_USER": "e2e-rustfs",
            "E2E_RUSTFS_PASSWORD": self.rustfs_password,
            "E2E_S3_ACCESS_KEY": self.s3_access,
        }

    # --- compose ---------------------------------------------------------------------------------------------------

    def compose(self, *args, timeout=900) -> subprocess.CompletedProcess:
        return subprocess.run(["docker", "compose", "-p", self.project, "-f", str(COMPOSE_FILE), *args],
                              env=self._env(), capture_output=True, text=True, timeout=timeout)

    def _chown_data(self) -> None:
        """The containers run as their own users; the folders must be theirs. Done in a container, as bootstrap does."""
        for folder, owner in (("idp", DATA_OWNERS["idp"]), ("rustfs", DATA_OWNERS["rustfs"]),
                              ("mongo", DATA_OWNERS["mongo"]), ("redis", DATA_OWNERS["redis"]),
                              ("elastic", DATA_OWNERS["elastic"])):
            subprocess.run(["docker", "run", "--rm", "-v", f"{self.state}/data:/data", "alpine:3.20", "sh", "-c",
                            f"chown -R {owner} /data/{folder}"], capture_output=True, timeout=300)

    def start(self) -> None:
        self.configure_settings()
        self.prepare()
        self._chown_data()
        result = self.compose("up", "-d", "idp")
        if result.returncode != 0:
            raise StackError(f"cannot start the sign-in service:\n{result.stderr[-3000:]}")
        self._wait(lambda: requests.get(f"{self.idp_url}/realms/mlops/.well-known/openid-configuration",
                                        timeout=10).status_code == 200, 240, "the sign-in service")
        self._identity()
        result = self.compose("up", "-d", "--build")
        if result.returncode != 0:
            raise StackError(f"cannot start the ClearML server:\n{result.stderr[-3000:]}")
        self._wait(self._api_answers, 600, "the ClearML API")
        self._wait(lambda: requests.get(self.web_url + "/", timeout=10).status_code == 200, 300, "the web app")

    def _identity(self) -> None:
        """The admin account (a realm user with the mlops-admin role) and the secret the server reads users with."""
        from .keycloak import Keycloak

        kc = Keycloak()
        kc.create_user(ADMIN_NAME, self.admin_password, admin=True)
        clients = kc._admin("GET", "/clients", params={"clientId": "clearml-server"}).json()
        client_uuid = clients[0]["id"]
        # The server reads users (for the directory sync) as its service account: it needs view-users, as bootstrap.sh
        # grants it. Without it the sync never sees a disabled account.
        service_user = kc._admin("GET", f"/clients/{client_uuid}/service-account-user").json()["id"]
        realm_management = kc._admin("GET", "/clients", params={"clientId": "realm-management"}).json()[0]["id"]
        view_users = kc._admin("GET", f"/clients/{realm_management}/roles/view-users").json()
        kc._admin("POST", f"/users/{service_user}/role-mappings/clients/{realm_management}",
                  json=[view_users]).raise_for_status()
        secret = kc._admin("GET", f"/clients/{client_uuid}/client-secret").json()["value"]
        (self.state / "secrets" / "idp_directory_secret").write_text(secret)
        (self.state / "secrets" / "idp_directory_secret").chmod(0o600)

    def _api_answers(self) -> bool:
        try:
            return requests.post(f"{self.api_url}/v2.8/login.supported_modes", json={}, timeout=10).status_code == 200
        except requests.RequestException:
            return False

    def _wait(self, check, timeout: float, what: str) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                if check():
                    return
            except requests.RequestException:
                pass
            time.sleep(3)
        logs = self.compose("logs", "--tail", "40").stdout[-3000:]
        raise StackError(f"{what} did not become ready in {timeout:.0f} s. Recent logs:\n{logs}")

    def stop(self) -> None:
        if self.keep:
            print(f"\nthe test stack is kept: {self.api_url} (state folder {self.state})")
            return
        self.compose("down", "--volumes", "--remove-orphans", timeout=600)
        self._remove_state()

    def _remove_state(self) -> None:
        """The containers wrote files as their own users; give them back to this user before removing them."""
        subprocess.run(["docker", "run", "--rm", "-v", f"{self.state}:/state", "alpine:3.20", "sh", "-c",
                        f"chown -R {os.getuid()}:{os.getgid()} /state"], capture_output=True, timeout=300)
        shutil.rmtree(self.state, ignore_errors=True)

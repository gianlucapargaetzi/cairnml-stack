"""A machine that runs jobs: its own HOME and device key, and the managed daemon running as a process."""

import os
import signal
import subprocess
import time
from pathlib import Path

from . import cli, settings
from .client import device_id_of, key_path

# How often the agent syncs with the test stack (the stack's scheduler is set to the same, in stack/compose.yaml).
SYNC_INTERVAL_SEC = 2


def shared_cache_settings() -> dict:
    """In the isolated environment (tests/e2e/docker) the agent's job containers are started by the nested daemon, which
    can only mount folders on the shared volume, at the same path as here. So the agent's caches and build folders are
    moved there. On the host (no MLOPS_E2E_SHARED_ROOT) the agent keeps its defaults."""
    shared = os.environ.get("MLOPS_E2E_SHARED_ROOT")
    if not shared:
        return {}
    cache = Path(shared) / "agent-cache"
    return {
        "CLEARML_AGENT__agent__venvs_dir": str(cache / "venvs-builds"),
        "CLEARML_AGENT__agent__venvs_cache__path": str(cache / "venvs-cache"),
        "CLEARML_AGENT__agent__vcs_cache__path": str(cache / "vcs-cache"),
        "CLEARML_AGENT__agent__pip_download_cache__path": str(cache / "pip-download-cache"),
        "CLEARML_AGENT__agent__docker_pip_cache": str(cache / "pip-cache"),
        "CLEARML_AGENT__agent__docker_apt_cache": str(cache / "apt-cache"),
    }


# A stopped agent is lost after three missed syncs, and the scheduler's sweep (every second on the test stack) finds it:
# about 6 s, with a generous margin.
LOST_WITHIN_SEC = 30


def init(home: Path, account):
    """clearml-agent init, signed in as account (user, password). Only an admin may enrol an agent.

    The command asks its questions on stdin: the web address, the web-app address, the API address, then the defaults
    (no output storage, no git login, no extra package index).
    """
    user, password = account
    answers = f"{settings.WEB_URL}\n{settings.WEB_URL}\n{settings.API_URL}\n" + "\n" * 8
    return cli.run("clearml-agent", home, login_user=user, login_password=password, args=["init"],
                   stdin_text=answers, timeout=300)


class AgentMachine:
    def __init__(self, home: Path, worker_name: str):
        self.home = home
        self.worker_name = worker_name
        self.log_path = home / "daemon.log"
        self._proc = None

    @property
    def device_id(self) -> str:
        return device_id_of(self.home)

    @property
    def key_path(self) -> Path:
        return key_path(self.home)

    def start(self) -> None:
        env = cli.environment(self.home)
        env["CLEARML_WORKER_NAME"] = self.worker_name
        # The test stack's scheduler syncs every 2 s (compose.yaml); the agent syncs at the same rate, so a worker is
        # registered and lost within seconds, not minutes (E2E.md, speed section, item 3).
        env["CLEARML_AGENT__services__scheduler__sync_interval_sec"] = str(SYNC_INTERVAL_SEC)
        env.update(shared_cache_settings())
        log = open(self.log_path, "ab")
        self._proc = subprocess.Popen(
            [str(cli.VENV_BIN / "clearml-agent"), "daemon", "--managed"],
            env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
        )

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def stop(self, timeout: float = 15) -> None:
        if not self.running:
            return
        os.killpg(self._proc.pid, signal.SIGTERM)
        try:
            self._proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(self._proc.pid, signal.SIGKILL)
            self._proc.wait(timeout=10)

    def log(self) -> str:
        return self.log_path.read_text(errors="replace") if self.log_path.exists() else ""

    def wait_until(self, condition, timeout: float = 60, poll: float = 1.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = condition()
            if value:
                return value
            time.sleep(poll)
        return None


def worker_record(api, worker_name: str):
    """This worker as the scheduler lists it, or None."""
    overview = api.authed("scheduler.get_overview", {})
    return next((w for w in overview.get("workers", []) if w.get("id") == worker_name), None)

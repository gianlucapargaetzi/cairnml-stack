"""A machine that runs jobs: its own HOME and device key, and the managed daemon running as a process."""

import os
import signal
import subprocess
import time
from pathlib import Path

from . import cli, settings
from .client import device_id_of, key_path


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
        log = open(self.log_path, "ab")
        self._proc = subprocess.Popen(
            [str(cli.VENV_BIN / "clearml-agent"), "daemon", "--managed"],
            env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
        )

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def stop(self, timeout: float = 60) -> None:
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

    def wait_until(self, condition, timeout: float = 180, poll: float = 3.0):
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

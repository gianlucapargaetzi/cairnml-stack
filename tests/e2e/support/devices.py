"""Enrolling, checking and signing out machines (clearml-init, clearml-whoami, clearml-logout)."""

import re
from pathlib import Path

from . import cli, settings

DEVICE_ID = re.compile(r"device (dev_[0-9a-f]{32})")


def key_path(home: Path) -> Path:
    return home / ".clearml" / "device.key"


def device_id_of(home: Path) -> str:
    """The device id this home is enrolled as, read from its configuration file."""
    conf = home / "clearml.conf"
    if not conf.is_file():
        return ""
    match = re.search(r'device_id\s*[:=]\s*"?(dev_[0-9a-f]{32})', conf.read_text())
    return match.group(1) if match else ""


def init(home: Path, *, user: str, password: str, server: str = None, name: str = "e2e-machine",
         force: bool = False):
    args = ["--server", server or settings.API_URL, "--name", name]
    if force:
        args.append("--force")
    return cli.run("clearml-init", home, login_user=user, login_password=password, args=args)


def whoami(home: Path):
    return cli.run("clearml-whoami", home)


def logout(home: Path):
    return cli.run("clearml-logout", home)

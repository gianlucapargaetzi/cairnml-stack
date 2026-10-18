"""Running the example scripts as a user would, and the project each session works in."""

import json
import os
from pathlib import Path

from . import cli, settings
from .api import Api

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def script(name: str) -> Path:
    return SCRIPTS / name


def run_json(home: Path, script_name: str, args=(), *, timeout=900, extra_env=None) -> dict:
    """Runs an example script in the given home. The script's last line is JSON; it is returned parsed."""
    result = cli.python(script(script_name), home, args=args, timeout=timeout, extra_env=extra_env)
    assert result.returncode == 0, f"{script_name} failed:\n{result.output[-4000:]}"
    return json.loads(result.stdout.strip().splitlines()[-1])


def run_raw(home: Path, script_name: str, args=(), *, timeout=900, extra_env=None):
    """Like run_json, but returns the process result (for the tests that expect a failure)."""
    return cli.python(script(script_name), home, args=args, timeout=timeout, extra_env=extra_env)


def device_api(home: Path) -> Api:
    """The REST client as the device enrolled in this home."""
    from .devices import device_id_of, key_path

    return Api(device_id_of(home), key_path(home))


def new_name(label: str) -> str:
    return f"{settings.PREFIX}-{label}-{os.urandom(3).hex()}"


def create_project(api: Api, name: str) -> str:
    return api.authed("projects.create", {"name": name})["id"]


def delete_project(api: Api, project_id: str) -> None:
    api.authed("projects.delete", {"project": project_id, "force": True, "delete_contents": True})

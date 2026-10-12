from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


class NotEnrolled(Exception):
    """No enrolled identity on this machine."""


def config_dir() -> Path:
    return Path(os.environ.get("MLOPS_CONFIG_DIR") or Path.home() / ".config" / "mlops")


def data_dir() -> Path:
    return Path(os.environ.get("MLOPS_DATA_DIR") or Path.home() / ".local" / "share" / "mlops")


def key_path() -> Path:
    return config_dir() / "key.pem"


def config_path() -> Path:
    return config_dir() / "config.json"


def spool_root() -> Path:
    return data_dir() / "spool"


@dataclass(frozen=True)
class ClientConfig:
    server_url: str
    client_id: str


def load_config() -> ClientConfig | None:
    if not config_path().exists():
        return None
    return ClientConfig(**json.loads(config_path().read_text()))


def save_config(cfg: ClientConfig) -> None:
    config_path().parent.mkdir(parents=True, exist_ok=True)
    config_path().write_text(json.dumps(asdict(cfg)))

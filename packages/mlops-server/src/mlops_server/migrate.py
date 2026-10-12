from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config


def _config(database_url: str) -> Config:
    here = Path(__file__).resolve().parent
    cfg = Config()
    cfg.set_main_option("script_location", str(here / "migrations"))
    cfg.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return cfg


def upgrade(database_url: str) -> None:
    command.upgrade(_config(database_url), "head")

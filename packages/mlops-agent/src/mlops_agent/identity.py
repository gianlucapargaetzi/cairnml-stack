from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from mlops_agent.config import AgentPaths


@dataclass(frozen=True)
class Identity:
    agent_id: str
    server_url: str


def save_identity(paths: AgentPaths, identity: Identity) -> None:
    paths.home.mkdir(parents=True, exist_ok=True)
    paths.identity.write_text(json.dumps(asdict(identity)))


def load_identity(paths: AgentPaths) -> Identity | None:
    if not paths.identity.exists():
        return None
    return Identity(**json.loads(paths.identity.read_text()))

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


@dataclass(frozen=True)
class AgentPaths:
    home: Path

    @property
    def key(self) -> Path:
        return self.home / "agent.key"

    @property
    def identity(self) -> Path:
        return self.home / "agent.json"

    @property
    def work(self) -> Path:
        return self.home / "work"


class AgentSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MLOPS_AGENT_")

    home: Path = Path("/var/lib/mlops-agent")
    server_url: str | None = None
    job_server_url: str | None = None
    job_network: str | None = None
    client_pip_spec: str = "mlops-client"
    wheels_dir: Path | None = None
    git_web_url: str = "https://github.com"
    poll_wait_s: int = 20
    heartbeat_s: int = 15
    labels: list[str] = []
    enroll_token: str | None = None
    name: str = "agent"
    dockerhub_user: str | None = None
    dockerhub_token: str | None = None

    @property
    def paths(self) -> AgentPaths:
        return AgentPaths(self.home)

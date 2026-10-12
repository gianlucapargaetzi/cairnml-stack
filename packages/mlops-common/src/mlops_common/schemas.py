"""Wire schemas shared by server, agent and client."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

RuntimeName = Literal["python", "image", "compose"]


class Capabilities(BaseModel):
    cpu: int = Field(ge=1)
    memory_gb: float = Field(gt=0)
    gpus: int = Field(default=0, ge=0)
    gpu_models: list[str] = []
    labels: list[str] = []
    runtimes: list[RuntimeName] = ["python", "image", "compose"]
    docker: bool = True


class PublicConfig(BaseModel):
    server_url: str
    oidc_issuer: str
    oidc_client_id: str


class ClientEnrollRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    public_key: str


class ClientEnrollResponse(BaseModel):
    client_id: str
    user_id: str
    username: str


class AgentTokenRequest(BaseModel):
    queues: list[str] = ["default"]
    ttl: int = Field(default=900, ge=60, le=86400)


class AgentTokenResponse(BaseModel):
    token: str
    expires_at: datetime


class AgentEnrollRequest(BaseModel):
    token: str
    name: str = Field(min_length=1, max_length=100)
    public_key: str
    capabilities: Capabilities


class AgentEnrollResponse(BaseModel):
    agent_id: str
    queues: list[str]


class TokenRequest(BaseModel):
    assertion: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int

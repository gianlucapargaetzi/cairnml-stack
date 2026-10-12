"""Wire schemas shared by server, agent and client."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

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


class ProjectCreate(BaseModel):
    slug: str = Field(
        max_length=100, pattern=r"^[a-z0-9][a-z0-9._-]*(/[a-z0-9][a-z0-9._-]*)?$"
    )
    name: str = Field(min_length=1, max_length=200)


class ProjectOut(BaseModel):
    slug: str
    name: str


class MemberAdd(BaseModel):
    project: str
    username: str


ExperimentStatus = Literal["created", "queued", "running", "finished", "failed", "cancelled"]
TERMINAL_STATUSES = {"finished", "failed", "cancelled"}


class GitInfo(BaseModel):
    repo: str | None = None  # "owner/name"
    remote_url: str | None = None
    commit: str | None = None
    branch: str | None = None
    dirty: bool = False
    cwd: str = "."  # working directory relative to the repo root
    patch_key: str | None = None  # object key of the uncommitted-changes patch


class DatasetRef(BaseModel):
    path: str
    dvc_hash: str | None = None
    repo: str | None = None
    commit: str | None = None


class ExperimentCreate(BaseModel):
    project: str
    name: str = Field(min_length=1, max_length=200)
    config: dict[str, Any] = {}
    source: Literal["local", "job"] = "local"
    parent_id: str | None = None


class ExperimentPatch(BaseModel):
    status: ExperimentStatus | None = None
    params: dict[str, Any] | None = None
    config: dict[str, Any] | None = None
    git: GitInfo | None = None
    datasets: list[DatasetRef] | None = None
    requirements: list[str] | None = None
    argv: list[str] | None = None
    env: dict[str, str] | None = None
    python_version: str | None = None
    platform: str | None = None
    script: str | None = None
    notes: str | None = None


class ExperimentOut(BaseModel):
    id: str
    project: str
    name: str
    status: ExperimentStatus
    source: str
    owner: str
    parent_id: str | None
    job_id: str | None
    config: dict[str, Any]
    params: dict[str, Any]
    git: GitInfo | None
    datasets: list[DatasetRef]
    requirements: list[str]
    argv: list[str]
    env: dict[str, str]
    python_version: str | None
    platform: str | None
    script: str | None
    notes: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class MetricPointIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    value: float = Field(allow_inf_nan=False)
    step: int | None = None
    ts: float = Field(allow_inf_nan=False)


class MetricBatch(BaseModel):
    points: list[MetricPointIn] = Field(min_length=1, max_length=5000)


class LogLine(BaseModel):
    ts: float = Field(allow_inf_nan=False)
    text: str


class LogBatch(BaseModel):
    stream: Literal["stdout", "stderr"]
    seq: int = Field(ge=0)
    lines: list[LogLine] = Field(min_length=1, max_length=5000)


class PresignRequest(BaseModel):
    name: str


class PresignResponse(BaseModel):
    upload_url: str
    key: str
    expires_in: int


ArtifactKind = Literal["file", "model", "script", "patch", "requirements", "log", "other"]


class ArtifactRegister(BaseModel):
    name: str
    key: str
    size: int = Field(default=0, ge=0)
    kind: ArtifactKind = "file"
    meta: dict[str, Any] = {}


class ArtifactOut(BaseModel):
    id: str
    name: str
    key: str
    size: int
    kind: ArtifactKind
    meta: dict[str, Any]


class StsRequest(BaseModel):
    project: str
    write: bool = False


class StsResponse(BaseModel):
    access_key: str
    secret_key: str
    session_token: str
    expires_at: datetime
    endpoint_url: str
    bucket: str
    prefix: str

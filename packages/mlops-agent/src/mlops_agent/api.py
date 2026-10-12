from __future__ import annotations

from typing import Any

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from mlops_common.http import KeyAuth, make_client
from mlops_common.schemas import (
    Capabilities,
    HeartbeatResponse,
    JobAssignment,
    StsResponse,
    TokenResponse,
)

from mlops_agent.identity import Identity


class AgentApi:
    def __init__(self, http: httpx.Client) -> None:
        self._http = http

    @classmethod
    def from_identity(
        cls,
        identity: Identity,
        key: Ed25519PrivateKey,
        transport: httpx.BaseTransport | None = None,
    ) -> AgentApi:
        auth = KeyAuth(identity.server_url, identity.agent_id, key)
        return cls(make_client(identity.server_url, auth=auth, transport=transport))

    def _post(self, path: str, json: Any = None, timeout: float | None = None) -> httpx.Response:
        kwargs = {} if timeout is None else {"timeout": timeout}
        response = self._http.post(path, json=json, **kwargs)
        response.raise_for_status()
        return response

    def heartbeat(
        self, running_job_ids: list[str], capabilities: Capabilities | None = None
    ) -> list[str]:
        body: dict[str, Any] = {"running_job_ids": running_job_ids}
        if capabilities is not None:
            body["capabilities"] = capabilities.model_dump()
        response = self._post("/api/v1/agents/heartbeat", body)
        return HeartbeatResponse.model_validate(response.json()).cancel_job_ids

    def poll(self, running_job_ids: list[str], wait_s: int) -> JobAssignment | None:
        response = self._post(
            "/api/v1/agents/poll",
            {"running_job_ids": running_job_ids, "wait_s": wait_s},
            timeout=wait_s + 15,
        )
        if response.status_code == 204:
            return None
        return JobAssignment.model_validate(response.json())

    def set_status(
        self,
        job_id: str,
        status: str,
        exit_code: int | None = None,
        message: str | None = None,
    ) -> None:
        self._post(
            f"/api/v1/jobs/{job_id}/status",
            {"status": status, "exit_code": exit_code, "message": message},
        )

    def run_token(self, job_id: str) -> str:
        response = self._post(f"/api/v1/jobs/{job_id}/run-token")
        return TokenResponse.model_validate(response.json()).access_token

    def git_token(self, job_id: str, repo: str) -> str:
        return self._post(f"/api/v1/jobs/{job_id}/git-token", {"repo": repo}).json()["token"]

    def sts(self, job_id: str) -> StsResponse:
        return StsResponse.model_validate(self._post(f"/api/v1/jobs/{job_id}/sts").json())

    def artifact_url(self, job_id: str, key: str) -> str:
        return self._post(f"/api/v1/jobs/{job_id}/artifact-url", {"key": key}).json()["url"]

    def post_logs(
        self, experiment_id: str, stream: str, seq: int, lines: list[dict[str, Any]]
    ) -> None:
        self._post(
            f"/api/v1/experiments/{experiment_id}/logs",
            {"stream": stream, "seq": seq, "lines": lines},
        )

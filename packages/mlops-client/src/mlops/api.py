from __future__ import annotations

import httpx
from mlops_common.http import KeyAuth, StaticTokenAuth
from mlops_common.keys import read_private_key
from mlops_common.schemas import StsResponse

from mlops.config import ClientConfig, NotEnrolled, key_path, load_config

_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


class ApiClient:
    def __init__(self, http: httpx.Client) -> None:
        self._http = http

    @classmethod
    def from_config(cls, config: ClientConfig | None = None) -> ApiClient:
        config = config or load_config()
        if config is None or not key_path().exists():
            raise NotEnrolled("this machine is not enrolled: run `mlops enroll --server <url>`")
        auth = KeyAuth(config.server_url, config.client_id, read_private_key(key_path()))
        return cls(httpx.Client(base_url=config.server_url, auth=auth, timeout=_TIMEOUT))

    @classmethod
    def from_run_token(cls, server_url: str, token: str) -> ApiClient:
        http = httpx.Client(
            base_url=server_url.rstrip("/"), auth=StaticTokenAuth(token), timeout=_TIMEOUT
        )
        return cls(http)

    @property
    def server_url(self) -> str:
        return str(self._http.base_url).rstrip("/")

    @staticmethod
    def _json(response: httpx.Response):
        response.raise_for_status()
        return response.json()

    def me(self) -> dict:
        return self._json(self._http.get("/api/v1/me"))

    def create_run(
        self,
        project: str,
        name: str,
        config: dict | None = None,
        source: str = "local",
        experiment: str = "general",
        primary_metric: str | None = None,
        direction: str | None = None,
    ) -> dict:
        body = {
            "project": project, "name": name, "config": config or {}, "source": source,
            "experiment": experiment,
        }
        if primary_metric:
            body.update(primary_metric=primary_metric, direction=direction)
        return self._json(self._http.post("/api/v1/runs", json=body))

    def get_run(self, run_id: str) -> dict:
        return self._json(self._http.get(f"/api/v1/runs/{run_id}"))

    def patch_run(self, run_id: str, **fields) -> dict:
        return self._json(self._http.patch(f"/api/v1/runs/{run_id}", json=fields))

    def list_runs(
        self, project: str | None = None, status: str | None = None, limit: int = 50
    ) -> list[dict]:
        params: dict = {"limit": limit}
        if project:
            params["project"] = project
        if status:
            params["status"] = status
        return self._json(self._http.get("/api/v1/runs", params=params))

    def list_experiments(self, project: str | None = None) -> list[dict]:
        return self._json(
            self._http.get("/api/v1/experiments", params={"project": project} if project else {})
        )

    def create_experiment(self, project: str, name: str, **fields) -> dict:
        return self._json(
            self._http.post(
                "/api/v1/experiments", json={"project": project, "name": name, **fields}
            )
        )

    def patch_experiment(self, experiment_id: str, **fields) -> dict:
        return self._json(self._http.patch(f"/api/v1/experiments/{experiment_id}", json=fields))

    def post_metrics(self, run_id: str, points: list[dict]) -> None:
        self._json(
            self._http.post(f"/api/v1/runs/{run_id}/metrics", json={"points": points})
        )

    def post_logs(self, run_id: str, stream: str, seq: int, lines: list[dict]) -> None:
        self._json(
            self._http.post(
                f"/api/v1/runs/{run_id}/logs",
                json={"stream": stream, "seq": seq, "lines": lines},
            )
        )

    def get_logs(self, run_id: str, after_seq: int = -1) -> list[dict]:
        return self._json(
            self._http.get(f"/api/v1/runs/{run_id}/logs", params={"after_seq": after_seq})
        )

    def presign(self, run_id: str, name: str) -> dict:
        return self._json(
            self._http.post(f"/api/v1/runs/{run_id}/artifacts/presign", json={"name": name})
        )

    def presign_sequence(
        self, run_id: str, kind: str, name: str, step: int, idx: int, fmt: str, context: dict
    ) -> dict:
        return self._json(
            self._http.post(
                f"/api/v1/runs/{run_id}/sequences/presign",
                json={"kind": kind, "name": name, "step": step, "idx": idx, "format": fmt,
                      "context": context},
            )
        )

    def post_sequences(self, run_id: str, items: list[dict]) -> dict:
        return self._json(
            self._http.post(f"/api/v1/runs/{run_id}/sequences", json={"items": items})
        )

    def register_artifact(
        self,
        run_id: str,
        name: str,
        key: str,
        size: int = 0,
        kind: str = "file",
        meta: dict | None = None,
    ) -> dict:
        return self._json(
            self._http.post(
                f"/api/v1/runs/{run_id}/artifacts",
                json={"name": name, "key": key, "size": size, "kind": kind, "meta": meta or {}},
            )
        )

    def list_artifacts(self, run_id: str) -> list[dict]:
        return self._json(self._http.get(f"/api/v1/runs/{run_id}/artifacts"))

    def create_job(self, spec: dict) -> dict:
        return self._json(self._http.post("/api/v1/jobs", json=spec))

    def get_job(self, job_id: str) -> dict:
        return self._json(self._http.get(f"/api/v1/jobs/{job_id}"))

    def cancel_job(self, job_id: str) -> dict:
        return self._json(self._http.post(f"/api/v1/jobs/{job_id}/cancel"))

    def get_job_spec(self, job_id: str) -> dict:
        return self._json(self._http.get(f"/api/v1/jobs/{job_id}/spec"))

    def reschedule_job(self, job_id: str, overrides: dict) -> dict:
        return self._json(self._http.post(f"/api/v1/jobs/{job_id}/reschedule", json=overrides))

    def sts(self, project: str, write: bool = False) -> StsResponse:
        return StsResponse.model_validate(
            self._json(
                self._http.post("/api/v1/storage/sts", json={"project": project, "write": write})
            )
        )

    def repo_status(self, repo: str, ref: str) -> dict:
        return self._json(self._http.get("/api/v1/repos/status", params={"repo": repo, "ref": ref}))

    def link_repo(self, project: str, repo: str, role: str = "code") -> dict:
        return self._json(
            self._http.post(
                "/api/v1/projects/repos", json={"project": project, "repo": repo, "role": role}
            )
        )

    def list_repos(self, project: str) -> list[dict]:
        return self._json(self._http.get("/api/v1/projects/repos", params={"project": project}))

    def list_datasets(self, project: str | None = None) -> list[dict]:
        params = {"project": project} if project else None
        return self._json(self._http.get("/api/v1/datasets", params=params))

    def get_dataset(self, project: str, repo: str, path: str) -> dict:
        params = {"project": project, "repo": repo, "path": path}
        return self._json(self._http.get("/api/v1/datasets/detail", params=params))

    def create_agent_token(self, queues: list[str], ttl: int = 900) -> dict:
        return self._json(
            self._http.post("/api/v1/admin/agent-tokens", json={"queues": queues, "ttl": ttl})
        )

    def create_project(self, slug: str, name: str) -> dict:
        return self._json(self._http.post("/api/v1/projects", json={"slug": slug, "name": name}))

    def add_member(self, project: str, username: str) -> dict:
        return self._json(
            self._http.post(
                "/api/v1/project-members", json={"project": project, "username": username}
            )
        )

    def list_agents(self) -> list[dict]:
        return self._json(self._http.get("/api/v1/admin/agents"))

    def list_clients(self) -> list[dict]:
        return self._json(self._http.get("/api/v1/admin/clients"))

    def revoke_agent(self, agent_id: str) -> dict:
        return self._json(self._http.post(f"/api/v1/admin/agents/{agent_id}/revoke"))

    def revoke_client(self, client_id: str) -> dict:
        return self._json(self._http.post(f"/api/v1/admin/clients/{client_id}/revoke"))

    def sync_users(self) -> dict:
        return self._json(self._http.post("/api/v1/admin/sync-users"))

"""Dispatch a recorded experiment to an agent from the client."""

from __future__ import annotations

import httpx
from mlops_common.dispatch import DispatchError, build_job_spec


def server_detail(exc: httpx.HTTPStatusError) -> str:
    try:
        return str(exc.response.json().get("detail", exc.response.text))
    except (ValueError, AttributeError):
        return exc.response.text


def dispatch_experiment(
    api,
    exp_id: str,
    *,
    queue: str = "default",
    resources: dict | None = None,
    env: dict | None = None,
) -> dict:
    exp = api.get_experiment(exp_id)
    spec = build_job_spec(
        exp, api.list_artifacts(exp_id), queue=queue, resources=resources, env=env
    )
    try:
        job = api.create_job(spec)
    except httpx.HTTPStatusError as exc:
        raise DispatchError(server_detail(exc)) from None
    api.patch_experiment(job["experiment_id"], notes=f"dispatched from {exp_id}")
    return job

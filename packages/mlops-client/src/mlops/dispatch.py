"""Turn a recorded experiment into a job spec an agent can run."""

from __future__ import annotations

import posixpath

import httpx

REDACTED = "***"


class DispatchError(Exception):
    pass


def server_detail(exc: httpx.HTTPStatusError) -> str:
    try:
        return str(exc.response.json().get("detail", exc.response.text))
    except (ValueError, AttributeError):
        return exc.response.text


def _python_minor(version: str | None) -> str:
    if not version:
        return "3.11"
    major, minor, *_ = version.split(".")
    return f"{major}.{minor}"


def _check_redacted(argv: list[str], params: dict) -> None:
    # The recorder replaces secrets with "***" (also inside "--flag=***" and URLs).
    # Dispatching such a value would run the job with a different command than the one
    # recorded, so refuse instead.
    for index, value in enumerate(argv):
        if isinstance(value, str) and REDACTED in value:
            raise DispatchError(
                f"argv[{index}] was redacted when the run was recorded "
                "(it looked like a secret); pass it through the environment instead"
            )
    for name, value in params.items():
        if value == REDACTED:
            raise DispatchError(
                f"parameter {name!r} was redacted when the run was recorded; "
                "it cannot be reproduced"
            )


def build_job_spec(
    exp: dict,
    artifacts: list[dict],
    *,
    queue: str = "default",
    resources: dict | None = None,
    name: str | None = None,
    env: dict | None = None,
) -> dict:
    git = exp.get("git")
    script = exp.get("script")
    argv = list(exp.get("argv") or [])
    tail = argv[1:]
    params = dict(exp.get("params") or {})
    flat = {**params.pop("args", {}), **params}
    _check_redacted(argv, flat)

    spec: dict = {
        "name": name or f"{exp['name']} (remote)",
        "project": exp["project"],
        "queue": queue,
        "resources": resources or {},
    }
    if env:
        spec["env"] = env
    if git and git.get("repo") and git.get("commit"):
        if not script:
            raise DispatchError("the experiment has git info but no script to run")
        workdir = git.get("cwd") or "."
        spec["code"] = {
            "repo": git["repo"],
            "commit": git["commit"],
            "workdir": workdir,
            "patch_key": git.get("patch_key"),
        }
        relative = posixpath.relpath(script, workdir)
        spec["runtime"] = {"type": "python", "command": ["python", relative, *tail]}
    else:
        if not script:
            raise DispatchError("the experiment has no git commit and no script to run")
        match = next(
            (a for a in artifacts if a.get("kind") == "script" and a.get("name") == script), None
        )
        if match is None:
            raise DispatchError(
                "the experiment has no script artifact to run; it was not recorded outside a repo"
            )
        spec["inputs"] = [{"key": match["key"], "dest": script}]
        spec["runtime"] = {"type": "python", "command": ["python", script, *tail]}
    spec["runtime"].update(
        python=_python_minor(exp.get("python_version")),
        requirements=list(exp.get("requirements") or []),
    )

    if flat:
        spec["params"] = flat
    if exp.get("datasets"):
        spec["data"] = exp["datasets"]
    return spec


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

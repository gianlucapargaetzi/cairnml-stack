"""Turn a recorded experiment into a job spec an agent can run (shared by client and server)."""

from __future__ import annotations

import posixpath

REDACTED = "***"


class DispatchError(Exception):
    pass


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
        "task": exp.get("task") or "general",
    }
    if env:
        spec["env"] = env
    # A script recorded as an artifact lives outside the checkout (the recorder uploads it
    # only then), so it is the input to run, even when git info is present.
    artifact = next(
        (a for a in artifacts if a.get("kind") == "script" and a.get("name") == script), None
    )
    has_repo = bool(git and git.get("repo") and git.get("commit"))
    if artifact is not None:
        spec["inputs"] = [{"key": artifact["key"], "dest": script}]
        spec["runtime"] = {"type": "python", "command": ["python", script, *tail]}
    elif has_repo:
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
    elif not script:
        raise DispatchError("the experiment has no git commit and no script to run")
    else:
        raise DispatchError(
            "the experiment has no script artifact to run; it was not recorded outside a repo"
        )
    spec["runtime"].update(
        python=_python_minor(exp.get("python_version")),
        requirements=list(exp.get("requirements") or []),
    )

    if flat:
        spec["params"] = flat
    if exp.get("datasets"):
        spec["data"] = exp["datasets"]
    return spec

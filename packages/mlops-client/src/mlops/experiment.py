"""Experiment lifecycle for local, offline and job runs."""

from __future__ import annotations

import atexit
import json
import logging
import os
import shutil
import sys
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx
from mlops_common.schemas import DatasetRef

from mlops import runtime
from mlops.capture import args as capargs
from mlops.capture.datasets import resolve_dataset
from mlops.capture.env import (
    capture_environment,
    capture_requirements,
    redact_argv,
    redact_mapping,
)
from mlops.capture.git import GitState, build_patch, capture_git
from mlops.capture.script import find_script, relative_cwd
from mlops.config import spool_root
from mlops.spool import Spool
from mlops.stdio import TeeStream
from mlops.uplink import Uplink

log = logging.getLogger("mlops")
_current: Experiment | None = None
_NETWORK = (httpx.TransportError, OSError)


class ExperimentError(Exception):
    pass


def current_experiment() -> Experiment | None:
    return _current


def _transient(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return isinstance(exc, _NETWORK)


class Experiment:
    def __init__(
        self,
        *,
        exp_id: str,
        project: str,
        name: str,
        api,
        mode: str,
        spool: Spool,
        git: GitState | None = None,
    ) -> None:
        self.id, self.project, self.name, self.mode = exp_id, project, name, mode
        self._api = api if mode != "offline" else None
        self._spool = spool
        self._git = git
        self._uplink = Uplink(self._api, None if mode == "offline" else exp_id, spool)
        self._datasets: list[DatasetRef] = []
        self._overrides: dict = {}
        self._failed = False
        self._interrupted = False
        self._closed = False
        self._saved_streams = None
        self._saved_hook = None
        self._lock = threading.Lock()

    # ----- server calls that must never crash user code -----
    def _spill(self, kind: str, payload: dict) -> None:
        try:
            self._spool.append(kind, payload)
        except (OSError, TypeError, ValueError) as exc:
            log.warning("could not spool a %s event, dropping it: %s", kind, exc)

    def _patch(self, **fields) -> None:
        if self._api is None:
            self._spill("patch", {"fields": fields})
            return
        try:
            self._api.patch_experiment(self.id, **fields)
        except Exception as exc:
            if _transient(exc):
                self._spill("patch", {"fields": fields})
            else:
                log.warning("server rejected experiment update: %s", exc)

    # ----- public API -----
    def log_metric(self, name: str, value: float, step: int | None = None) -> None:
        self._uplink.metric(name, value, step)

    def log_metrics(self, values: dict, step: int | None = None) -> None:
        for name, value in values.items():
            self._uplink.metric(name, value, step)

    def log_params(self, params: dict) -> None:
        self._patch(params=redact_mapping(json.loads(json.dumps(params, default=str))))

    def connect(self, params):
        if self.mode == "job" and self._overrides:
            capargs.apply_overrides(params, self._overrides)
        self.log_params(params if isinstance(params, dict) else vars(params))
        return params

    def use_dataset(self, path) -> DatasetRef:
        ref = resolve_dataset(path, self._git)
        self._datasets.append(ref)
        self._patch(datasets=[d.model_dump() for d in self._datasets])
        return ref

    def upload_artifact(
        self, name: str, path=None, obj=None, kind: str = "file", meta: dict | None = None
    ):
        from mlops import transfer

        if (path is None) == (obj is None):
            raise ValueError("pass exactly one of path= or obj=")
        if ".." in name.split("/") or name.startswith("/"):
            raise ValueError("invalid artifact name")
        if path is not None:
            source = Path(path)
            if not source.is_file():
                raise ValueError("path must be an existing file")
            size = source.stat().st_size
        else:
            source = (
                obj
                if isinstance(obj, bytes)
                else (obj.encode() if isinstance(obj, str) else json.dumps(obj).encode())
            )
            size = len(source)
        try:
            if self._api is None:
                raise httpx.ConnectError("offline")
            presigned = self._api.presign(self.id, name)
            transfer.put_file(presigned["upload_url"], source)
            self._api.register_artifact(self.id, name, presigned["key"], size, kind, meta)
            return presigned["key"]
        except Exception as exc:
            if not _transient(exc):
                log.warning("artifact %s was rejected: %s", name, exc)
                return None
            self._spill_artifact(name, source, kind, meta, size)
            return None

    def _spill_artifact(self, name: str, source, kind: str, meta: dict | None, size: int) -> None:
        try:
            target = self._spool.file_path(name)
            if isinstance(source, bytes):
                target.write_bytes(source)
            else:
                shutil.copyfile(source, target)
            self._spool.append(
                "artifact", {"name": name, "kind": kind, "meta": meta or {}, "size": size}
            )
        except (OSError, TypeError, ValueError) as exc:
            log.warning("could not spool artifact %s, dropping it: %s", name, exc)

    def execute_remotely(
        self, queue: str = "default", resources: dict | None = None, exit_process: bool = True
    ) -> dict | None:
        """Re-run this script on an agent. In job mode (already on an agent) it returns None."""
        from mlops.dispatch import dispatch_experiment

        if self.mode == "job":
            return None
        if self.mode == "offline":
            raise ExperimentError("cannot dispatch while the server is unreachable")
        self._uplink.flush()
        try:
            job = dispatch_experiment(self._api, self.id, queue=queue, resources=resources)
        except Exception as exc:
            # Close as failed so the run is not recorded as "finished" when the caller
            # catches the error. Re-raise: the caller decides what happens next.
            self._patch(notes=f"dispatch failed: {exc}")
            self.close(status="failed")
            raise
        self._patch(notes=f"continued remotely as {job['experiment_id']}")
        self.close(status="cancelled")
        print(f"dispatched as job {job['id']} (experiment {job['experiment_id']})")
        if exit_process:
            raise SystemExit(0)
        return job

    def close(self, status: str | None = None) -> None:
        global _current
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._restore()
        capargs.uninstall()
        try:
            self._uplink.close()
        except Exception as exc:
            log.warning("some telemetry could not be delivered or spooled: %s", exc)
        if self.mode != "job":
            final = status or (
                "cancelled" if self._interrupted else "failed" if self._failed else "finished"
            )
            self._patch(status=final)
        if _current is self:
            _current = None
        try:
            atexit.unregister(self.close)
        except Exception:
            pass

    def __enter__(self) -> Experiment:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is not None:
            self._failed = exc_type is not KeyboardInterrupt
            self._interrupted = exc_type is KeyboardInterrupt
        self.close()

    # ----- process hooks -----
    def _install_hooks(self, capture_stdout: bool, capture_args: bool) -> None:
        if capture_stdout and self.mode != "job":
            self._saved_streams = (sys.stdout, sys.stderr)
            sys.stdout = TeeStream(sys.stdout, lambda line: self._uplink.log("stdout", line))
            sys.stderr = TeeStream(sys.stderr, lambda line: self._uplink.log("stderr", line))
        if capture_args:
            capargs.install(
                lambda values: self._patch(params={"args": redact_mapping(values)}),
                overrides=self._overrides or None,
            )
        previous = sys.excepthook

        def hook(exc_type, exc, tb):
            self._failed = not issubclass(exc_type, KeyboardInterrupt)
            self._interrupted = issubclass(exc_type, KeyboardInterrupt)
            previous(exc_type, exc, tb)

        self._saved_hook = previous
        sys.excepthook = hook
        atexit.register(self.close)
        self._uplink.start()

    def _restore(self) -> None:
        if self._saved_streams is not None:
            for stream in (sys.stdout, sys.stderr):
                if isinstance(stream, TeeStream):
                    stream.flush_partial()
            sys.stdout, sys.stderr = self._saved_streams
            self._saved_streams = None
        if self._saved_hook is not None:
            sys.excepthook = self._saved_hook
            self._saved_hook = None


def _capture_step(what: str, fn, *args):
    """Run one capture step. A failure is logged and the step is skipped (returns None)."""
    try:
        return fn(*args)
    except Exception as exc:
        log.warning("could not capture %s, continuing without it: %s", what, exc)
        return None


def _error_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:300]
    if isinstance(body, dict):
        return str(body.get("detail", response.text))[:300]
    return response.text[:300]


def init(
    project: str,
    name: str,
    config: dict | None = None,
    *,
    script=None,
    capture_stdout: bool = True,
    capture_args: bool = True,
    capture_git: bool = True,
    datasets: list[str] | None = None,
    api=None,
    task: str = "general",
    primary_metric: str | None = None,
    direction: str | None = None,
) -> Experiment:
    """Start recording. In a job run the task comes from the experiment record instead."""
    global _current
    token, exp_id = os.environ.get("MLOPS_RUN_TOKEN"), os.environ.get("MLOPS_EXPERIMENT_ID")
    if token and exp_id:
        experiment = _init_job(project, name, token, exp_id, capture_args)
    else:
        experiment = _init_local(
            project, name, config, script, capture_stdout, capture_args, capture_git, datasets, api,
            task, primary_metric, direction,
        )
    _current = experiment
    return experiment


def _job_overrides() -> dict:
    raw = os.environ.get("MLOPS_PARAMS") or "{}"
    try:
        overrides = json.loads(raw)
    except ValueError as exc:  # the message names the position, never the value
        log.warning("ignoring MLOPS_PARAMS, it is not valid JSON: %s", exc)
        return {}
    if not isinstance(overrides, dict):
        log.warning("ignoring MLOPS_PARAMS, it must be a JSON object")
        return {}
    return overrides


def _init_job(project, name, token, exp_id, capture_args) -> Experiment:
    api = runtime.make_api(token, os.environ.get("MLOPS_SERVER_URL"))
    experiment = Experiment(
        exp_id=exp_id,
        project=project,
        name=name,
        api=api,
        mode="job",
        spool=Spool(spool_root() / exp_id, {"experiment_id": exp_id}),
    )
    experiment._overrides = _job_overrides()
    experiment._install_hooks(capture_stdout=False, capture_args=capture_args)
    return experiment


def _init_local(
    project, name, config, script, capture_stdout, capture_args, want_git, datasets, api,
    task="general", primary_metric=None, direction=None,
) -> Experiment:
    # NotEnrolled from make_api() is deliberately not guarded: no enrollment is a setup error.
    api = api or runtime.make_api()
    probe = _capture_step("script location", find_script, script)
    start = probe.path.parent if probe else Path.cwd()
    git = _capture_step("git state", capture_git, start) if want_git else None
    script_info = _capture_step("script location", find_script, script, git)

    mode, exp_id = "local", None
    try:
        exp_id = api.create_experiment(
            project, name, config or {}, task=task, primary_metric=primary_metric,
            direction=direction,
        )["id"]
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code < 500:
            raise ExperimentError(
                f"could not create experiment in project {project!r}: {_error_detail(exc.response)}"
            ) from None
        mode = "offline"
    except (ValueError, KeyError, TypeError) as exc:  # 2xx with a non-JSON or unexpected body
        raise ExperimentError(f"unreadable reply creating experiment: {exc}") from None
    except _NETWORK:
        mode = "offline"
    if mode == "offline":
        exp_id = f"offline_{uuid.uuid4().hex[:12]}"
        log.warning("server unreachable: running offline, data is spooled (run `mlops sync` later)")
    meta = {
        "local_id": exp_id,
        "experiment_id": None if mode == "offline" else exp_id,
        "project": project,
        "name": name,
        "config": config or {},
        "task": task,
        "primary_metric": primary_metric,
        "direction": direction,
        "created_at": datetime.now(UTC).isoformat(),
    }
    experiment = Experiment(
        exp_id=exp_id,
        project=project,
        name=name,
        api=api,
        mode=mode,
        spool=Spool(spool_root() / exp_id, meta),
        git=git,
    )

    fields = _reproduction_fields(experiment, git, script_info)
    for dataset in datasets or []:
        ref = _capture_step("dataset", resolve_dataset, dataset, git)
        if ref is not None:
            experiment._datasets.append(ref)
    if experiment._datasets:
        fields["datasets"] = [d.model_dump() for d in experiment._datasets]
    experiment._patch(**fields, status="running")
    experiment._install_hooks(capture_stdout, capture_args)
    return experiment


def _reproduction_fields(experiment: Experiment, git: GitState | None, script) -> dict:
    fields: dict = {}
    requirements = _capture_step("requirements", capture_requirements)
    if requirements is not None:
        fields["requirements"] = requirements
    argv = _capture_step("arguments", redact_argv, list(sys.argv))
    if argv is not None:
        fields["argv"] = argv
    env = _capture_step("environment", capture_environment)
    if env is not None:
        fields["python_version"] = env["python_version"]
        fields["platform"] = env["platform"]
        fields["env"] = {"cpu_count": str(env["cpu_count"]), "gpus": ", ".join(env["gpus"])}
    if git is not None:
        git_fields = _capture_step("git state", _git_fields, experiment, git, script)
        if git_fields is not None:
            fields["git"] = git_fields
    if script is not None:
        script_field = _capture_step("script", _script_field, experiment, script)
        if script_field is not None:
            fields["script"] = script_field
    return fields


def _git_fields(experiment: Experiment, git: GitState, script) -> dict:
    patch_key = None
    if git.dirty:
        patch = _capture_step("uncommitted changes", build_patch, git.root)
        if patch is not None:
            patch_key = experiment.upload_artifact("uncommitted.patch", obj=patch, kind="patch")
            if patch_key is None:
                patch_key = f"{experiment.project}/{experiment.id}/uncommitted.patch"
    return {
        "repo": git.repo,
        "remote_url": git.remote_url,
        "commit": git.commit,
        "branch": git.branch,
        "dirty": git.dirty,
        "cwd": relative_cwd(git, script.path.parent if script else None),
        "patch_key": patch_key,
    }


def _script_field(experiment: Experiment, script) -> str:
    if script.in_repo:
        return script.rel
    experiment.upload_artifact(script.path.name, path=script.path, kind="script")
    return script.path.name

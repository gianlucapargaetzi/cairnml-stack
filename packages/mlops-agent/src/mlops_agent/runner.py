"""The job pipeline: prepare the workspace, run the executor, report the outcome."""

from __future__ import annotations

import json
import shutil
import threading
from collections.abc import Callable
from pathlib import Path

from mlops_common.schemas import JobAssignment

from mlops_agent.api import AgentApi
from mlops_agent.config import AgentSettings
from mlops_agent.dvc import dataset_targets, dvc_pull
from mlops_agent.executors.base import BaseExecutor, RunContext
from mlops_agent.logship import LogShipper
from mlops_agent.workspace import apply_patch, clone_at, download, safe_join


class JobRunner:
    def __init__(
        self,
        api: AgentApi,
        settings: AgentSettings,
        make_executor: Callable[[str], BaseExecutor],
        download_fn=download,
        dvc_pull_fn=dvc_pull,
    ) -> None:
        self._api = api
        self._settings = settings
        self._make_executor = make_executor
        self._download = download_fn
        self._dvc_pull = dvc_pull_fn
        self._active: dict[str, BaseExecutor] = {}
        self._cancel_requested: set[str] = set()
        self._lock = threading.Lock()
        self._timeout_scale = 1.0  # tests shrink timeouts

    def cancel(self, job_id: str) -> None:
        with self._lock:
            self._cancel_requested.add(job_id)
            executor = self._active.get(job_id)
        if executor is not None:
            executor.cancel()

    def _prepare(self, a: JobAssignment, root: Path, secrets: list[str]) -> Path:
        spec = a.spec
        if spec.code:
            token = self._api.git_token(a.job_id, spec.code.repo)
            secrets.append(token)  # registered before the clone so git output is scrubbed
            clone_at(spec.code.repo, spec.code.commit, root, token, self._settings.git_web_url)
            if spec.code.patch_key:
                patch_file = root.parent / f"{a.job_id}.patch"
                self._download(self._api.artifact_url(a.job_id, spec.code.patch_key), patch_file)
                try:
                    apply_patch(root, patch_file.read_bytes())
                finally:
                    patch_file.unlink(missing_ok=True)
        for item in spec.inputs:
            self._download(self._api.artifact_url(a.job_id, item.key), safe_join(root, item.dest))
        if spec.data:
            targets = dataset_targets(
                spec.data,
                spec.code.repo if spec.code else None,
                spec.code.commit if spec.code else None,
            )
            sts = self._api.sts(a.job_id)
            secrets.extend([sts.secret_key, sts.session_token])
            self._dvc_pull(root, targets, sts)
        return safe_join(root, spec.code.workdir) if spec.code else root

    def _env(self, a: JobAssignment, secrets: list[str]) -> dict[str, str]:
        token = self._api.run_token(a.job_id)
        secrets.append(token)
        # MLOPS_* keys are set after spec.env so user-supplied env cannot override them.
        return {
            **a.spec.env,
            "MLOPS_SERVER_URL": self._settings.job_server_url or self._settings.server_url or "",
            "MLOPS_RUN_TOKEN": token,
            "MLOPS_EXPERIMENT_ID": a.experiment_id,
            "MLOPS_JOB_ID": a.job_id,
            "MLOPS_PARAMS": json.dumps(a.spec.params),
        }

    def run(self, a: JobAssignment) -> None:
        secrets: list[str] = []

        def scrub(text: str) -> str:
            for secret in secrets:
                if secret:
                    text = text.replace(secret, "***")
            return text

        def post(stream: str):
            return lambda s, seq, lines: self._api.post_logs(a.experiment_id, s, seq, lines)

        out = LogShipper(post("stdout"), "stdout", scrub=scrub)
        err = LogShipper(post("stderr"), "stderr", scrub=scrub)
        root = self._settings.paths.work / a.job_id
        status, exit_code, message = "failed", None, None
        executor: BaseExecutor | None = None
        timer: threading.Timer | None = None
        timed_out = threading.Event()
        try:
            self._api.set_status(a.job_id, "running")
            out.start()
            err.start()
            root.mkdir(parents=True, exist_ok=True)
            workdir = self._prepare(a, root, secrets)
            env = self._env(a, secrets)
            executor = self._make_executor(a.spec.runtime.type)
            with self._lock:
                self._active[a.job_id] = executor
                cancelled_early = a.job_id in self._cancel_requested
            if cancelled_early:
                executor.cancel()
            if a.spec.timeout_s:

                def on_timeout() -> None:
                    timed_out.set()
                    executor.cancel()

                timer = threading.Timer(a.spec.timeout_s * self._timeout_scale, on_timeout)
                timer.daemon = True
                timer.start()
            ctx = RunContext(
                a.job_id,
                a.experiment_id,
                a.spec,
                root,
                workdir,
                env,
                out.write,
                err.write,
                self._settings,
            )
            exit_code = executor.run(ctx) if not cancelled_early else 130
            if executor.cancelled and not timed_out.is_set():
                status = (
                    "cancelled"  # cancelled wins over any exit code: never finished after cancel
                )
            elif timed_out.is_set():
                status, message = "failed", f"timed out after {a.spec.timeout_s} s"
            elif exit_code == 0:
                status = "finished"
            else:
                status, message = "failed", f"exit code {exit_code}"
        except Exception as exc:
            message = scrub(str(exc))[:1000]
            err.write(f"mlops-agent: {message}")
            if executor is not None and executor.cancelled and not timed_out.is_set():
                status = "cancelled"
        finally:
            if timer is not None:
                timer.cancel()
            with self._lock:
                self._active.pop(a.job_id, None)
                self._cancel_requested.discard(a.job_id)
            out.close()
            err.close()
            shutil.rmtree(root, ignore_errors=True)
            self._api.set_status(a.job_id, status, exit_code, message)

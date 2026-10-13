"""The job pipeline: prepare the workspace, run the executor, report the outcome."""

from __future__ import annotations

import json
import logging
import shutil
import threading
import time
from collections.abc import Callable
from pathlib import Path

import httpx
from mlops_common.schemas import JobAssignment

from mlops_agent.api import AgentApi
from mlops_agent.config import AgentSettings
from mlops_agent.dvc import dataset_targets, dvc_pull
from mlops_agent.executors.base import BaseExecutor, RunContext
from mlops_agent.logship import LogShipper
from mlops_agent.workspace import apply_patch, clone_at, download, safe_join

log = logging.getLogger(__name__)

# Waits before each retry of the final status: four attempts in total.
_FINAL_BACKOFF_S = (0.5, 1.0, 2.0)


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
        self._sleep = time.sleep  # tests replace it to skip the backoff

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
            secrets.extend([sts.access_key, sts.secret_key, sts.session_token])
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
            "MLOPS_RUN_ID": a.run_id,
            "MLOPS_JOB_ID": a.job_id,
            "MLOPS_PARAMS": json.dumps(a.spec.params),
        }

    def _report_final(
        self, job_id: str, status: str, exit_code: int | None, message: str | None
    ) -> None:
        """Send the terminal status, retrying transient failures. Never raises."""
        for attempt, delay in enumerate((0.0, *_FINAL_BACKOFF_S), start=1):
            if delay:
                self._sleep(delay)
            try:
                self._api.set_status(job_id, status, exit_code, message)
                return
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code < 500:
                    # 4xx (for example 409 after a reap) will not change on retry.
                    log.error("server rejected final status %s for job %s: %s", status, job_id, exc)
                    return
                log.warning(
                    "final status %s for job %s, attempt %d: %s", status, job_id, attempt, exc
                )
            except httpx.TransportError as exc:
                log.warning(
                    "final status %s for job %s, attempt %d: %s", status, job_id, attempt, exc
                )
            except Exception:
                log.exception("could not send final status %s for job %s", status, job_id)
                return
        log.error("giving up on final status %s for job %s", status, job_id)

    def run(self, a: JobAssignment) -> None:
        secrets: list[str] = []

        def scrub(text: str) -> str:
            for secret in secrets:
                if secret:
                    text = text.replace(secret, "***")
            return text

        def post(stream: str):
            return lambda s, seq, lines: self._api.post_logs(a.run_id, s, seq, lines)

        out = LogShipper(post("stdout"), "stdout", scrub=scrub)
        err = LogShipper(post("stderr"), "stderr", scrub=scrub)
        root = self._settings.paths.work / a.job_id
        timeout_s = a.spec.timeout_s
        executor: BaseExecutor | None = None
        timer: threading.Timer | None = None
        timed_out = threading.Event()
        returned = threading.Event()  # set once the outcome is decided: a late timer is a no-op
        gate = threading.Lock()  # orders the timer's flag against the decision
        error: str | None = None
        exit_code: int | None = None
        try:
            self._api.set_status(a.job_id, "running")
            out.start()
            err.start()
            root.mkdir(parents=True, exist_ok=True)
            workdir = self._prepare(a, root, secrets)
            env = self._env(a, secrets)
            if self._settings.dockerhub_token:
                secrets.append(self._settings.dockerhub_token)  # before the executor can log in
            executor = self._make_executor(a.spec.runtime.type)
            with self._lock:
                self._active[a.job_id] = executor
                cancelled_early = a.job_id in self._cancel_requested
            if cancelled_early:
                executor.cancel()
            if timeout_s:

                def on_timeout() -> None:
                    with gate:
                        if returned.is_set():
                            return
                        timed_out.set()
                    executor.cancel()

                timer = threading.Timer(timeout_s * self._timeout_scale, on_timeout)
                timer.daemon = True
                timer.start()
            ctx = RunContext(
                a.job_id,
                a.run_id,
                a.spec,
                root,
                workdir,
                env,
                out.write,
                err.write,
                self._settings,
            )
            exit_code = 130 if cancelled_early else executor.run(ctx)
        except Exception as exc:
            error = scrub(str(exc))[:1000]
            err.write(f"mlops-agent: {error}")
        finally:
            with gate:
                returned.set()
                timed = timed_out.is_set()  # one snapshot: the decision uses only this
            if timer is not None:
                timer.cancel()
            with self._lock:
                cancelled = a.job_id in self._cancel_requested
                self._active.pop(a.job_id, None)
                self._cancel_requested.discard(a.job_id)
            out.close()
            err.close()
            shutil.rmtree(root, ignore_errors=True)
            # Priority: cancel, then timeout, then an error, then the exit code.
            if cancelled:
                status, message = "cancelled", error
            elif timed:
                status, message = "failed", f"timed out after {timeout_s} s"
            elif error is not None:
                status, message = "failed", error
            elif exit_code == 0:
                status, message = "finished", None
            else:
                status, message = "failed", f"exit code {exit_code}"
            self._report_final(a.job_id, status, exit_code, message)

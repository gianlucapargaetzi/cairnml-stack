import io
import subprocess

import pytest
from mlops_agent.config import AgentSettings
from mlops_agent.executors.base import RunContext
from mlops_agent.executors.compose import ComposeExecutor
from mlops_common.schemas import JobSpec


class FakeProc:
    def __init__(self, code=0, out="up\n", err="warn\n"):
        self.stdout, self.stderr, self._code, self.terminated = (
            io.StringIO(out),
            io.StringIO(err),
            code,
            False,
        )

    def wait(self):
        return 143 if self.terminated else self._code

    def terminate(self):
        self.terminated = True


def _ctx(tmp_path, file="compose.yaml"):
    spec = JobSpec.model_validate(
        {
            "name": "j",
            "project": "p/q",
            "code": {"repo": "o/r", "commit": "a" * 40},
            "runtime": {"type": "compose", "file": file, "service": "trainer"},
        }
    )
    root = tmp_path / "job"
    root.mkdir()
    out, err = [], []
    ctx = RunContext(
        "job_3",
        "exp_3",
        spec,
        root,
        root,
        {"MLOPS_RUN_TOKEN": "tok"},
        out.append,
        err.append,
        AgentSettings(home=tmp_path),
    )
    return ctx, out, err


def test_up_streams_logs_and_always_tears_down(tmp_path):
    ctx, out, err = _ctx(tmp_path)
    started, downs = {}, []

    def popen(cmd, **kw):
        started.update(cmd=cmd, **kw)
        return FakeProc(code=5)

    code = ComposeExecutor(
        popen=popen,
        run=lambda cmd, **kw: downs.append(cmd) or subprocess.CompletedProcess(cmd, 0),
    ).run(ctx)
    assert code == 5 and out == ["up"] and err == ["warn"]
    assert started["cmd"][:5] == ["docker", "compose", "-p", "mlops-job_3", "-f"]
    assert started["cmd"][-5:] == [
        "up",
        "--build",
        "--abort-on-container-exit",
        "--exit-code-from",
        "trainer",
    ]
    assert started["env"]["MLOPS_RUN_TOKEN"] == "tok" and started["cwd"] == ctx.workdir
    assert downs[0][-3:] == ["down", "-v", "--remove-orphans"]


def test_teardown_runs_even_if_popen_fails(tmp_path):
    ctx, *_ = _ctx(tmp_path)
    downs = []

    def popen(cmd, **kw):
        raise OSError("docker missing")

    with pytest.raises(OSError):
        ComposeExecutor(popen=popen, run=lambda cmd, **kw: downs.append(cmd)).run(ctx)
    assert downs


def test_compose_file_must_stay_inside_the_workspace(tmp_path):
    ctx, *_ = _ctx(tmp_path, file="../../etc/compose.yaml")
    with pytest.raises(ValueError):
        ComposeExecutor(popen=lambda *a, **k: FakeProc(), run=lambda *a, **k: None).run(ctx)


def test_cancel_terminates_the_process(tmp_path):
    ctx, *_ = _ctx(tmp_path)
    proc = FakeProc()
    executor = ComposeExecutor(popen=lambda cmd, **kw: proc, run=lambda *a, **k: None)
    executor._proc = proc
    executor.cancel()
    assert proc.terminated and executor.cancelled


def test_cancel_before_registration_terminates_once_registered(tmp_path):
    ctx, *_ = _ctx(tmp_path)
    proc = FakeProc(code=0)
    executor = ComposeExecutor(popen=lambda cmd, **kw: proc, run=lambda *a, **k: None)
    executor.cancel()  # no process registered yet
    assert not proc.terminated
    executor.run(ctx)
    assert proc.terminated


def test_only_allowlisted_host_env_reaches_compose(tmp_path, monkeypatch):
    monkeypatch.setenv("MLOPS_AGENT_ENROLL_TOKEN", "sentinel-secret")
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    ctx, *_ = _ctx(tmp_path)
    started, downs = {}, []

    def popen(cmd, **kw):
        started.update(kw)
        return FakeProc()

    ComposeExecutor(
        popen=popen, run=lambda cmd, **kw: downs.append(kw) or subprocess.CompletedProcess(cmd, 0)
    ).run(ctx)
    for env in (started["env"], downs[0]["env"]):
        assert "MLOPS_AGENT_ENROLL_TOKEN" not in env
        assert "sentinel-secret" not in env.values()
        assert env["PATH"] == "/usr/bin:/bin"
        assert env["MLOPS_RUN_TOKEN"] == "tok"

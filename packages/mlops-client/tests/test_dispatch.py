import sys

import httpx
import mlops
import pytest
from mlops import runtime
from mlops.api import ApiClient
from mlops.capture import args as capargs
from mlops.cli import app as cli
from mlops.dispatch import DispatchError, build_job_spec
from mlops.run import RunError
from mlops.testing import git, make_repo
from typer.testing import CliRunner

SHA = "a" * 40


def _exp(**overrides):
    base = {
        "id": "run_1",
        "project": "vision/seg",
        "name": "baseline",
        "status": "finished",
        "git": {
            "repo": "owner/name",
            "commit": SHA,
            "dirty": True,
            "cwd": "src",
            "patch_key": "vision/seg/run_1/uncommitted.patch",
        },
        "script": "src/train.py",
        "argv": ["src/train.py", "--lr", "0.1"],
        "python_version": "3.11.9",
        "requirements": ["numpy==1.26.4"],
        "params": {"args": {"lr": 0.1, "epochs": 2}, "seed": 7},
        "datasets": [
            {"path": "data/train", "dvc_hash": "abc.dir", "repo": "owner/name", "commit": SHA}
        ],
    }
    return {**base, **overrides}


def test_build_job_spec_from_a_repo_run():
    spec = build_job_spec(_exp(), [], queue="gpu", resources={"cpu": 4, "gpu": 1})
    assert (
        spec["name"] == "baseline (remote)"
        and spec["queue"] == "gpu"
        and spec["project"] == "vision/seg"
    )
    assert spec["code"] == {
        "repo": "owner/name",
        "commit": SHA,
        "workdir": "src",
        "patch_key": "vision/seg/run_1/uncommitted.patch",
    }
    assert spec["runtime"] == {
        "type": "python",
        "python": "3.11",
        "requirements": ["numpy==1.26.4"],
        "command": ["python", "train.py", "--lr", "0.1"],
    }
    assert spec["params"] == {"lr": 0.1, "epochs": 2, "seed": 7}
    assert spec["resources"] == {"cpu": 4, "gpu": 1} and spec["data"][0]["dvc_hash"] == "abc.dir"
    assert "inputs" not in spec or spec["inputs"] == []


def test_build_job_spec_for_a_script_outside_a_repo():
    exp = _exp(git=None, script="run.py", argv=["run.py", "--n", "3"], datasets=[])
    artifacts = [
        {"name": "run.py", "kind": "script", "key": "vision/seg/run_1/run.py"}
    ]
    spec = build_job_spec(exp, artifacts)
    assert "code" not in spec or spec["code"] is None
    assert spec["inputs"] == [{"key": "vision/seg/run_1/run.py", "dest": "run.py"}]
    assert spec["runtime"]["command"] == ["python", "run.py", "--n", "3"]


def test_script_artifact_wins_over_git_info():
    # A script outside the checkout is uploaded as an artifact and recorded by basename.
    # The commit does not contain it, so it must run as an input, not from the checkout.
    exp = _exp(script="run.py", argv=["run.py", "--n", "3"])
    artifacts = [
        {"name": "run.py", "kind": "script", "key": "vision/seg/run_1/run.py"}
    ]
    spec = build_job_spec(exp, artifacts)
    assert spec["inputs"] == [{"key": "vision/seg/run_1/run.py", "dest": "run.py"}]
    assert spec["runtime"]["command"] == ["python", "run.py", "--n", "3"]
    assert "code" not in spec


def test_build_job_spec_refuses_what_it_cannot_reproduce():
    with pytest.raises(DispatchError, match=r"argv\[2\].*redacted"):
        build_job_spec(_exp(argv=["src/train.py", "--api-key", "***"]), [])
    with pytest.raises(DispatchError, match="no git commit and no script"):
        build_job_spec(_exp(git=None, script=None), [])
    with pytest.raises(DispatchError, match="script artifact"):
        build_job_spec(_exp(git=None, script="x.py"), [])


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    run = mlops.current_run()
    if run is not None:
        run.close()
    capargs.uninstall()


def test_execute_remotely_reproduces_a_dirty_local_run(sdk, stub_github, tmp_path, monkeypatch):
    work, _ = make_repo(tmp_path, {"train.py": "print(1)\n"})
    (work / "train.py").write_text("print(2)\n")
    monkeypatch.chdir(work)
    monkeypatch.setattr(sys, "argv", ["train.py", "--lr", "0.1"])
    sha = git("rev-parse", "HEAD", cwd=work)
    stub_github.commits.add(("owner/name", sha))
    run = mlops.init("vision/seg", "to-remote", script=work / "train.py")
    with pytest.raises(SystemExit) as stop:
        run.execute_remotely(queue="gpu", resources={"cpu": 2})
    assert stop.value.code == 0
    local = sdk.api.get_run(run.id)
    assert local["status"] == "cancelled" and "continued remotely as run_" in local["notes"]
    runs = sdk.api.list_runs("vision/seg")
    remote = next(e for e in runs if e["source"] == "job")
    assert (
        remote["git"]["commit"] == sha
        and remote["git"]["patch_key"] == f"vision/seg/{run.id}/uncommitted.patch"
    )
    assert remote["notes"] == f"dispatched from {run.id}"
    job = sdk.api.get_job(remote["job_id"])
    assert job["queue"] == "gpu" and job["status"] == "queued"


def test_execute_remotely_surfaces_unpushed_commit(sdk, stub_github, tmp_path, monkeypatch):
    work, _ = make_repo(tmp_path)
    monkeypatch.chdir(work)
    run = mlops.init(
        "vision/seg", "unpushed", script=work / "train.py"
    )  # stub_github does not know the commit
    with pytest.raises(DispatchError, match="push it first"):
        run.execute_remotely(exit_process=False)
    local = sdk.api.get_run(run.id)
    assert local["status"] == "failed" and "dispatch failed" in local["notes"]


def test_execute_remotely_is_a_noop_in_job_mode_and_offline_is_refused(sdk, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run = mlops.init("vision/seg", "x")
    run.mode = "offline"
    with pytest.raises(RunError, match="unreachable"):
        run.execute_remotely()
    run.mode = "job"
    assert run.execute_remotely() is None
    run.mode = "local"


def test_cli_dispatch_ls_job_and_logs(sdk, stub_github):
    stub_github.commits.add(("owner/name", SHA))
    exp = sdk.api.create_run("vision/seg", "cli-source")
    sdk.api.patch_run(
        exp["id"],
        git={"repo": "owner/name", "commit": SHA, "cwd": ".", "dirty": False},
        script="train.py",
        argv=["train.py"],
        python_version="3.11.9",
        requirements=[],
    )
    runner = CliRunner()
    out = runner.invoke(
        cli, ["dispatch", exp["id"], "--queue", "default", "--cpu", "2", "--memory-gb", "4"]
    )
    assert out.exit_code == 0 and "job_" in out.output
    job_id = next(w for w in out.output.split() if w.startswith("job_"))
    assert "queued" in runner.invoke(cli, ["job", "show", job_id]).output
    assert "cancelled" in runner.invoke(cli, ["job", "cancel", job_id]).output
    assert "cli-source" in runner.invoke(cli, ["ls", "--project", "vision/seg"]).output
    sdk.api.post_logs(exp["id"], "stdout", 0, [{"ts": 1.0, "text": "hello log"}])
    assert "hello log" in runner.invoke(cli, ["logs", exp["id"]]).output


def test_cli_dispatch_file_and_server_errors(sdk, stub_github, tmp_path):
    spec = tmp_path / "job.yaml"
    spec.write_text(
        "name: img\nproject: vision/seg\nruntime:\n  type: image\n"
        "  image: alpine:3.20\n  command: [echo, hi]\n"
    )
    runner = CliRunner()
    ok = runner.invoke(cli, ["dispatch", "--file", str(spec)])
    assert ok.exit_code == 0 and "job_" in ok.output
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        f"name: x\nproject: vision/seg\ncode: {{repo: o/r, commit: '{'b' * 40}'}}\n"
        "runtime: {type: python, command: [python, x.py]}\n"
    )
    failed = runner.invoke(cli, ["dispatch", "--file", str(bad)])
    assert failed.exit_code == 1 and "push it first" in failed.output


def test_cli_reports_unreachable_server_in_one_line(cfg_env, monkeypatch):
    unreachable = ApiClient(httpx.Client(base_url="http://127.0.0.1:9", timeout=2.0))
    monkeypatch.setattr(runtime, "make_api", lambda *a, **k: unreachable)
    out = CliRunner().invoke(cli, ["ls"])
    assert out.exit_code == 1 and "cannot reach http://127.0.0.1:9" in out.output
    assert "Traceback" not in out.output


def test_cli_reports_not_enrolled_in_one_line(cfg_env):
    runtime.set_api_override(None)
    out = CliRunner().invoke(cli, ["job", "show", "job_x"])
    assert out.exit_code == 1 and "not enrolled: run mlops enroll" in out.output
    assert "Traceback" not in out.output


def test_job_spec_keeps_the_experiment_of_the_run():
    spec = build_job_spec(_exp(experiment="evaluation"), [])
    assert spec["experiment"] == "evaluation"
    assert build_job_spec(_exp(experiment=None), [])["experiment"] == "general"


def test_cli_experiment_commands(sdk):
    runner = CliRunner()
    sdk.api.create_run("vision/seg", "e", experiment="training")
    assert "training" in runner.invoke(cli, ["experiment", "ls", "--project", "vision/seg"]).output
    result = runner.invoke(
        cli,
        ["experiment", "set", "vision/seg", "training",
         "--metric", "val_loss", "--direction", "min"],
    )
    assert result.exit_code == 0
    experiments = {t["name"]: t for t in sdk.api.list_experiments("vision/seg")}
    assert experiments["training"]["primary_metric"] == "val_loss"

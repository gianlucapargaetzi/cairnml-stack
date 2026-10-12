import argparse
import json
import logging
import sys

import httpx
import mlops
import pytest
from mlops import runtime
from mlops.api import ApiClient
from mlops.capture import args as capargs
from mlops.config import NotEnrolled
from mlops.experiment import ExperimentError
from mlops.spool import Spool
from mlops.stdio import TeeStream
from mlops.testing import git, make_repo


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    experiment = mlops.current_experiment()
    if experiment is not None:
        experiment.close()
    capargs.uninstall()


def _exp(sdk, experiment):
    return sdk.api.get_experiment(experiment.id)


def test_tee_stream_reports_lines_and_progress_bars():
    seen, sink = [], []

    class Out:
        def write(self, s):
            sink.append(s)
            return len(s)

        def flush(self):
            pass

        encoding = "utf-8"

    tee = TeeStream(Out(), seen.append)
    tee.write("a\nb")
    tee.write("c\n")
    tee.write("10%\r50%\r100%\n")
    tee.write("tail")
    tee.flush_partial()
    assert seen == ["a", "bc", "100%", "tail"] and "".join(sink) == "a\nbc\n10%\r50%\r100%\ntail"
    assert tee.encoding == "utf-8"


def test_local_run_records_reproduction_metadata(sdk, tmp_path, monkeypatch):
    work, _ = make_repo(tmp_path, {"train.py": "print(1)\n", "requirements.txt": "numpy\n"})
    (work / "train.py").write_text("print(2)\n")  # dirty tree
    monkeypatch.chdir(work)
    monkeypatch.setattr(sys, "argv", ["train.py", "--lr", "0.1", "--api-key", "SECRET"])
    experiment = mlops.init("vision/seg", "baseline", {"lr": 0.1}, script=work / "train.py")
    exp = _exp(sdk, experiment)
    assert exp["status"] == "running" and exp["config"] == {"lr": 0.1} and exp["source"] == "local"
    assert (
        exp["git"]["commit"] == git("rev-parse", "HEAD", cwd=work) and exp["git"]["dirty"] is True
    )
    assert exp["git"]["repo"] == "owner/name" and exp["git"]["cwd"] == "."
    assert exp["git"]["patch_key"] == f"vision/seg/{experiment.id}/uncommitted.patch"
    assert exp["script"] == "train.py" and exp["argv"] == [
        "train.py",
        "--lr",
        "0.1",
        "--api-key",
        "***",
    ]
    assert exp["python_version"].count(".") == 2 and isinstance(exp["requirements"], list)
    assert any(b"print(2)" in data for _, data in sdk.uploads)
    experiment.close()
    assert _exp(sdk, experiment)["status"] == "finished"


def test_clean_repo_uploads_no_patch(sdk, tmp_path, monkeypatch):
    work, _ = make_repo(tmp_path)
    monkeypatch.chdir(work)
    experiment = mlops.init("vision/seg", "clean", script=work / "train.py")
    assert _exp(sdk, experiment)["git"]["patch_key"] is None and not sdk.uploads
    experiment.close()


def test_script_outside_a_repo_is_uploaded_as_an_artifact(sdk, tmp_path, monkeypatch):
    loose = tmp_path / "loose" / "experiment.py"
    loose.parent.mkdir()
    loose.write_text("print('loose')\n")
    monkeypatch.chdir(loose.parent)
    experiment = mlops.init("vision/seg", "loose", script=loose)
    exp = _exp(sdk, experiment)
    assert exp["git"] is None and exp["script"] == "experiment.py"
    artifacts = sdk.api.list_artifacts(experiment.id)
    assert [(a["name"], a["kind"]) for a in artifacts] == [("experiment.py", "script")]
    assert sdk.uploads[0][1] == b"print('loose')\n"
    experiment.close()


def test_metrics_stdout_and_params_are_logged(sdk, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    original_out, original_err = sys.stdout, sys.stderr
    experiment = mlops.init("vision/seg", "m")
    experiment.log_metric("loss", 0.5, step=1)
    experiment.log_metrics({"acc": 0.9, "f1": 0.8}, step=1)
    experiment.log_params({"batch": 32})
    print("hello training")
    print("oops", file=sys.stderr)
    experiment.close()
    series = sdk.dev.http.get(f"/api/v1/experiments/{experiment.id}/metrics").json()
    assert set(series) == {"loss", "acc", "f1"}
    logs = {"stdout": [], "stderr": []}
    for chunk in sdk.api.get_logs(experiment.id):
        logs[chunk["stream"]].extend(line["text"] for line in chunk["lines"])
    assert "hello training" in logs["stdout"] and "oops" in logs["stderr"]
    assert _exp(sdk, experiment)["params"]["batch"] == 32
    assert sys.stdout is original_out and sys.stderr is original_err  # streams restored by identity
    assert "hello training" in capsys.readouterr().out  # and the user still saw the output


def test_uncaught_exception_marks_failed_and_keyboard_interrupt_cancelled(
    sdk, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    experiment = mlops.init("vision/seg", "boom")
    sys.excepthook(ValueError, ValueError("x"), None)
    experiment.close()
    assert _exp(sdk, experiment)["status"] == "failed"
    task2 = mlops.init("vision/seg", "ctrl-c")
    sys.excepthook(KeyboardInterrupt, KeyboardInterrupt(), None)
    task2.close()
    assert _exp(sdk, task2)["status"] == "cancelled"


def test_argparse_args_are_recorded(sdk, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    experiment = mlops.init("vision/seg", "args")
    parser = argparse.ArgumentParser()
    parser.add_argument("--lr", type=float, default=0.1)
    parser.parse_args(["--lr", "0.3"])
    experiment.close()
    assert _exp(sdk, experiment)["params"]["args"] == {"lr": 0.3}


def test_use_dataset_records_the_dvc_hash(sdk, tmp_path, monkeypatch):
    work, _ = make_repo(
        tmp_path, {"data/train.dvc": "outs:\n- md5: abc123.dir\n  path: train\n", "train.py": "x\n"}
    )
    monkeypatch.chdir(work)
    experiment = mlops.init("vision/seg", "ds", script=work / "train.py")
    ref = experiment.use_dataset("data/train")
    assert ref.dvc_hash == "abc123.dir"
    with pytest.raises(ValueError, match="not tracked"):
        experiment.use_dataset("data/missing")
    experiment.close()
    assert _exp(sdk, experiment)["datasets"][0]["dvc_hash"] == "abc123.dir"


def test_upload_artifact_variants_and_unsafe_names(sdk, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    experiment = mlops.init("vision/seg", "art")
    model = tmp_path / "m.pt"
    model.write_bytes(b"weights")
    assert (
        experiment.upload_artifact("ckpt/m.pt", path=model, kind="model", meta={"epoch": 1})
        == f"vision/seg/{experiment.id}/ckpt/m.pt"
    )
    experiment.upload_artifact("cfg.json", obj={"a": 1})
    experiment.upload_artifact("note.txt", obj="hello")
    names = {a["name"]: a for a in sdk.api.list_artifacts(experiment.id)}
    assert names["ckpt/m.pt"]["kind"] == "model" and names["ckpt/m.pt"]["meta"] == {"epoch": 1}
    assert json.loads(
        dict((u.rsplit("/", 1)[-1].split("?")[0], d) for u, d in sdk.uploads)["cfg.json"]
    ) == {"a": 1}
    with pytest.raises(ValueError):
        experiment.upload_artifact("../escape", obj="x")
    with pytest.raises(ValueError):
        experiment.upload_artifact("dir", path=tmp_path)
    experiment.close()


def test_init_requires_enrollment(cfg_env):
    with pytest.raises(NotEnrolled):
        mlops.init("vision/seg", "x")


def test_unknown_project_is_a_clear_error(sdk, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ExperimentError, match="vision/nope"):
        mlops.init("vision/nope", "x")


def test_server_down_at_init_runs_offline_and_spools(cfg_env, monkeypatch, tmp_path):
    def down(request):
        raise httpx.ConnectError("refused")

    api = ApiClient(
        httpx.Client(base_url="http://mlops-server:8000", transport=httpx.MockTransport(down))
    )
    runtime.set_api_override(lambda token, url: api)
    monkeypatch.chdir(tmp_path)
    try:
        experiment = mlops.init("vision/seg", "offline-run")
        assert experiment.mode == "offline" and experiment.id.startswith("offline_")
        experiment.log_metric("loss", 1.0, 0)
        print("still training")
        experiment.close()
    finally:
        runtime.set_api_override(None)
    spool = Spool(tmp_path / "data" / "spool" / experiment.id)
    kinds = [e["kind"] for e in spool.events()]
    assert {"metrics", "logs", "patch"} <= set(kinds)
    assert spool.meta()["project"] == "vision/seg" and spool.meta()["name"] == "offline-run"


def test_server_dying_mid_run_does_not_raise(sdk, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    experiment = mlops.init("vision/seg", "mid")
    experiment._api = ApiClient(
        httpx.Client(
            base_url="http://x",
            transport=httpx.MockTransport(
                lambda r: (_ for _ in ()).throw(httpx.ConnectError("gone"))
            ),
        )
    )
    experiment._uplink._api = experiment._api
    experiment.log_metric("loss", 1.0, 0)
    experiment.upload_artifact("late.txt", obj="data")  # must not raise
    experiment.close()
    kinds = [e["kind"] for e in experiment._spool.events()]
    assert "metrics" in kinds and "artifact" in kinds


def test_job_mode_attaches_applies_overrides_and_leaves_status_alone(
    sdk, make_agent, new_job, app, monkeypatch, tmp_path
):
    from fastapi.testclient import TestClient
    from mlops_common.http import StaticTokenAuth

    agent = make_agent()
    job = new_job(sdk.dev.http)
    agent.http.post("/api/v1/agents/poll", json={"wait_s": 0})
    agent.http.post(f"/api/v1/jobs/{job['id']}/status", json={"status": "running"})
    token = agent.http.post(f"/api/v1/jobs/{job['id']}/run-token").json()["access_token"]
    run_http = TestClient(app)
    run_http.auth = StaticTokenAuth(token)
    runtime.set_api_override(lambda tok, url: ApiClient(run_http) if tok else sdk.api)
    monkeypatch.setenv("MLOPS_RUN_TOKEN", token)
    monkeypatch.setenv("MLOPS_EXPERIMENT_ID", job["experiment_id"])
    monkeypatch.setenv("MLOPS_SERVER_URL", "http://testserver")
    monkeypatch.setenv("MLOPS_PARAMS", json.dumps({"lr": "0.9", "epochs": 4}))
    monkeypatch.chdir(tmp_path)

    experiment = mlops.init("ignored", "ignored")
    assert experiment.mode == "job" and experiment.id == job["experiment_id"]
    assert not isinstance(sys.stdout, TeeStream)  # the agent captures stdout in jobs
    cfg = experiment.connect({"lr": 0.1, "epochs": 1, "keep": "x"})
    assert cfg == {"lr": 0.9, "epochs": 4, "keep": "x"}
    ns = experiment.connect(argparse.Namespace(lr=0.1, epochs=1))
    assert (ns.lr, ns.epochs) == (0.9, 4)
    experiment.log_metric("loss", 0.1, 0)
    experiment.close()
    exp = sdk.api.get_experiment(job["experiment_id"])
    assert exp["status"] == "running"  # only the agent changes the status in job mode
    assert "loss" in sdk.dev.http.get(f"/api/v1/experiments/{job['experiment_id']}/metrics").json()


def test_tee_stream_strips_crlf_line_endings():
    seen = []

    class Out:
        def write(self, s):
            return len(s)

        def flush(self):
            pass

    tee = TeeStream(Out(), seen.append)
    tee.write("hello\r\nworld\r\n")
    tee.write("partial\r")
    tee.flush_partial()
    assert seen == ["hello", "world", "partial"]


def test_git_missing_does_not_break_init(sdk, tmp_path, monkeypatch):
    import subprocess

    work, _ = make_repo(tmp_path)
    monkeypatch.chdir(work)

    def no_git(*args, **kwargs):
        raise FileNotFoundError(2, "No such file or directory", "git")

    monkeypatch.setattr(subprocess, "run", no_git)
    experiment = mlops.init("vision/seg", "nogit", script=work / "train.py")
    experiment.log_metric("loss", 1.0, 0)
    experiment.close()
    exp = _exp(sdk, experiment)
    assert exp["git"] is None and exp["status"] == "finished"


def test_bad_mlops_params_do_not_raise(sdk, tmp_path, monkeypatch):
    monkeypatch.setenv("MLOPS_RUN_TOKEN", "run-token-value")
    monkeypatch.setenv("MLOPS_EXPERIMENT_ID", "exp_missing")
    monkeypatch.setenv("MLOPS_PARAMS", "{not json")
    monkeypatch.chdir(tmp_path)
    experiment = mlops.init("vision/seg", "badparams")
    assert experiment.mode == "job"
    assert experiment.connect({"lr": 0.1}) == {"lr": 0.1}
    experiment.close()
    monkeypatch.setenv("MLOPS_PARAMS", "[1, 2]")
    experiment = mlops.init("vision/seg", "badparams-list")
    assert experiment.connect({"lr": 0.1}) == {"lr": 0.1}
    experiment.close()


def test_unconvertible_job_override_keeps_the_default(sdk, tmp_path, monkeypatch):
    monkeypatch.setenv("MLOPS_RUN_TOKEN", "run-token-value")
    monkeypatch.setenv("MLOPS_EXPERIMENT_ID", "exp_missing")
    monkeypatch.setenv("MLOPS_PARAMS", json.dumps({"epochs": "abc", "lr": "0.9"}))
    monkeypatch.chdir(tmp_path)
    experiment = mlops.init("vision/seg", "cast")
    cfg = experiment.connect({"epochs": 1, "lr": 0.1})
    assert cfg == {"epochs": 1, "lr": 0.9}
    ns = experiment.connect(argparse.Namespace(epochs=1, lr=0.1))
    assert (ns.epochs, ns.lr) == (1, 0.9)
    experiment.close()


def test_unwritable_spool_never_raises(cfg_env, monkeypatch, tmp_path):
    def down(request):
        raise httpx.ConnectError("refused")

    api = ApiClient(
        httpx.Client(base_url="http://mlops-server:8000", transport=httpx.MockTransport(down))
    )
    runtime.set_api_override(lambda token, url: api)
    monkeypatch.chdir(tmp_path)
    # A regular file where the spool directory should be makes every spool write fail.
    (cfg_env / "data").mkdir(exist_ok=True)
    (cfg_env / "data" / "spool").write_text("not a directory")
    try:
        experiment = mlops.init("vision/seg", "unwritable")
        assert experiment.mode == "offline"
        experiment.log_metric("loss", 1.0, 0)
        experiment.log_params({"batch": 8})
        experiment.upload_artifact("late.txt", obj="data")
        experiment.close()  # none of these may raise
    finally:
        runtime.set_api_override(None)


def test_non_json_artifact_meta_is_dropped_not_raised(sdk, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    experiment = mlops.init("vision/seg", "meta")
    experiment._api = ApiClient(
        httpx.Client(
            base_url="http://x",
            transport=httpx.MockTransport(
                lambda r: (_ for _ in ()).throw(httpx.ConnectError("gone"))
            ),
        )
    )
    experiment._uplink._api = experiment._api
    assert experiment.upload_artifact("odd.txt", obj="x", meta={"bad": object()}) is None
    experiment.close()


def test_non_json_4xx_body_becomes_experiment_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    api = ApiClient(
        httpx.Client(
            base_url="http://x",
            transport=httpx.MockTransport(
                lambda r: httpx.Response(400, text="<html>bad request</html>")
            ),
        )
    )
    with pytest.raises(ExperimentError, match="bad request"):
        mlops.init("vision/seg", "bad", api=api)


def test_uplink_warnings_stay_out_of_captured_stderr(sdk, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    experiment = mlops.init("vision/seg", "feedback")

    class Rejecting:
        def post_logs(self, *args, **kwargs):
            raise httpx.HTTPStatusError(
                "rejected", request=httpx.Request("POST", "http://x"), response=httpx.Response(400)
            )

    # A root handler on the stderr tee, as a user's basicConfig() would install.
    user_handler = logging.StreamHandler(sys.stderr)
    logging.getLogger().addHandler(user_handler)
    try:
        experiment._uplink._api = Rejecting()
        experiment._uplink._exp = experiment.id
        print("to stderr", file=sys.stderr)
        experiment._uplink.flush()  # the server rejects the batch and the uplink warns
        assert experiment._uplink._lines["stderr"] == []  # the warning did not loop back
    finally:
        logging.getLogger().removeHandler(user_handler)
        experiment.close()


def test_run_token_is_absent_from_the_spool(cfg_env, monkeypatch, tmp_path):
    secret = "run-token-SECRET-value-123"

    def down(request):
        raise httpx.ConnectError("refused")

    api = ApiClient(
        httpx.Client(base_url="http://mlops-server:8000", transport=httpx.MockTransport(down))
    )
    runtime.set_api_override(lambda token, url: api)
    monkeypatch.setenv("MLOPS_RUN_TOKEN", secret)
    monkeypatch.setenv("MLOPS_EXPERIMENT_ID", "exp_job")
    monkeypatch.setenv("MLOPS_SERVER_URL", "http://mlops-server:8000")
    monkeypatch.chdir(tmp_path)
    try:
        experiment = mlops.init("vision/seg", "tokens")
        experiment.log_metric("loss", 1.0, 0)
        experiment.close()
    finally:
        runtime.set_api_override(None)
    spool_dir = cfg_env / "data" / "spool" / "exp_job"
    files = [p for p in spool_dir.rglob("*") if p.is_file()]
    assert files and not any(secret.encode() in p.read_bytes() for p in files)


def test_non_json_2xx_create_reply_becomes_experiment_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    api = ApiClient(
        httpx.Client(
            base_url="http://x",
            transport=httpx.MockTransport(
                lambda r: httpx.Response(200, text="<html>captive portal</html>")
            ),
        )
    )
    with pytest.raises(ExperimentError, match="unreadable reply"):
        mlops.init("vision/seg", "html-reply", api=api)


def test_init_records_the_task_and_its_primary_metric(sdk, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    experiment = mlops.init(
        "vision/seg", "t1", task="training", primary_metric="val_loss", direction="min"
    )
    assert sdk.api.get_experiment(experiment.id)["task"] == "training"
    tasks = {t["name"]: t for t in sdk.api.list_tasks("vision/seg")}
    assert tasks["training"]["primary_metric"] == "val_loss"
    experiment.close()


def test_the_default_task_is_general(sdk, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    experiment = mlops.init("vision/seg", "t2")
    assert sdk.api.get_experiment(experiment.id)["task"] == "general"
    experiment.close()

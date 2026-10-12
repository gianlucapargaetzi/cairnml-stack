import shutil
import subprocess
from pathlib import Path

import httpx
import mlops
import pytest
import yaml
from mlops import runtime
from mlops import transfer as transfer_module
from mlops.api import ApiClient
from mlops.cli import app as cli
from mlops.config import spool_root
from mlops.data import dvc_command
from mlops.repo import find_project, init_repo
from mlops.spool import Spool
from mlops.sync import sync_all
from mlops.testing import make_repo
from typer.testing import CliRunner

REAL_PUT = transfer_module.put_file  # captured before the sdk fixture patches it


class Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, cmd, **kwargs):
        self.calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")


def test_init_repo_writes_project_file_and_configures_the_remote(sdk, stub_github, tmp_path):
    work, _ = make_repo(tmp_path)
    stub_github.add_repo("owner/name")
    stub_github.heads[("owner/name", "HEAD")] = "a" * 40
    run = Recorder()
    result = init_repo(work, "vision/seg", sdk.api, run=run, which=lambda name: "/usr/bin/dvc")
    assert yaml.safe_load((work / ".mlops" / "project.yaml").read_text())["project"] == "vision/seg"
    commands = [c for c, _ in run.calls]
    assert ["dvc", "init", "-q"] in commands
    assert ["dvc", "remote", "add", "-f", "-d", "storage", "s3://datasets/vision/seg"] in commands
    assert ["dvc", "remote", "modify", "storage", "endpointurl", "https://nas.test"] in commands
    assert (
        result["remote_url"] == "s3://datasets/vision/seg" and result["github_app"] == "installed"
    )
    assert find_project(work / "sub" if (work / "sub").exists() else work) == "vision/seg"


def test_repo_init_links_the_repository(sdk, stub_github, tmp_path):
    work, _ = make_repo(tmp_path)
    stub_github.add_repo("owner/name")
    stub_github.heads[("owner/name", "HEAD")] = "a" * 40
    init_repo(work, "vision/seg", sdk.api, run=Recorder(), which=lambda name: "/usr/bin/dvc")
    assert sdk.api.list_repos("vision/seg") == [
        {"project": "vision/seg", "repo": "owner/name", "role": "code"}
    ]


def test_link_repo_command_records_the_role(sdk, stub_github, cfg_env):
    stub_github.add_repo("org/data")
    result = CliRunner().invoke(
        cli, ["repo", "link", "--project", "vision/seg", "--repo", "org/data", "--role", "data"]
    )
    assert result.exit_code == 0, result.output
    assert sdk.api.list_repos("vision/seg") == [
        {"project": "vision/seg", "repo": "org/data", "role": "data"}
    ]


def test_init_repo_reports_missing_github_app_and_non_repos(sdk, stub_github, tmp_path):
    work, _ = make_repo(tmp_path)
    stub_github.inaccessible.add("owner/name")
    result = init_repo(
        work, "vision/seg", sdk.api, run=Recorder(), which=lambda name: "/usr/bin/dvc"
    )
    assert result["github_app"] == "not installed"
    with pytest.raises(ValueError, match="git repository"):
        init_repo(
            tmp_path, "vision/seg", sdk.api, run=Recorder(), which=lambda name: "/usr/bin/dvc"
        )
    with pytest.raises(ValueError, match="not an mlops repo"):
        find_project(tmp_path)


def test_dvc_commands_use_temporary_credentials_only_in_the_environment(
    sdk, stub_storage, tmp_path
):
    run = Recorder()
    dvc_command(
        sdk.api,
        "vision/seg",
        "push",
        ["data/train"],
        tmp_path,
        run=run,
        which=lambda n: "/usr/bin/dvc",
    )
    cmd, kwargs = run.calls[0]
    assert cmd == ["dvc", "push", "data/train"] and kwargs["env"]["AWS_ACCESS_KEY_ID"] == "AK"
    assert stub_storage.sts_calls[-1] == ("vision/seg", True)
    dvc_command(
        sdk.api, "vision/seg", "pull", [], tmp_path, run=run, which=lambda n: "/usr/bin/dvc"
    )
    assert stub_storage.sts_calls[-1] == ("vision/seg", False)
    with pytest.raises(ValueError):
        dvc_command(
            sdk.api, "vision/seg", "delete", [], tmp_path, run=run, which=lambda n: "/usr/bin/dvc"
        )


def test_dvc_failure_is_scrubbed(sdk, tmp_path):
    def failing(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="denied for SK / ST")

    with pytest.raises(RuntimeError) as err:
        dvc_command(
            sdk.api, "vision/seg", "pull", [], tmp_path, run=failing, which=lambda n: "/usr/bin/dvc"
        )
    assert "SK" not in str(err.value).replace("denied", "") and "ST" not in str(err.value).replace(
        "denied", ""
    )


def _offline_task(tmp_path, monkeypatch, **init_options):
    def down(request):
        raise httpx.ConnectError("refused")

    broken = ApiClient(
        httpx.Client(base_url="http://mlops-server:8000", transport=httpx.MockTransport(down))
    )
    previous = runtime._override
    runtime.set_api_override(lambda token, url: broken)
    monkeypatch.chdir(tmp_path)
    try:
        # capture_git=False: the script lives in this (possibly dirty) checkout, and a dirty
        # state would add an uncommitted.patch artifact that the assertions do not expect.
        experiment = mlops.init(
            "vision/seg", "offline-run", {"lr": 0.1}, capture_git=False, **init_options
        )
        experiment.log_metric("loss", 0.25, 3)
        print("offline line")
        experiment.upload_artifact("out.txt", obj="saved while offline")
        experiment.close()
    finally:
        runtime.set_api_override(previous)
    return experiment


def test_sync_replays_an_offline_run_exactly_once(sdk, tmp_path, monkeypatch):
    experiment = _offline_task(tmp_path, monkeypatch)
    puts = []

    def record(url, source, http=None):
        # sync streams a path; read it here to check the uploaded content.
        puts.append(source.read_bytes() if isinstance(source, Path) else source)

    synced = sync_all(sdk.api, put=record)
    assert len(synced) == 1
    exp = sdk.api.get_experiment(synced[0])
    assert (
        exp["name"] == "offline-run"
        and exp["config"] == {"lr": 0.1}
        and exp["status"] == "finished"
    )
    assert (
        sdk.dev.http.get(f"/api/v1/experiments/{synced[0]}/metrics").json()["loss"][0]["value"]
        == 0.25
    )
    texts = [line["text"] for chunk in sdk.api.get_logs(synced[0]) for line in chunk["lines"]]
    assert "offline line" in texts
    # The launching script may also be uploaded (it lives outside the repo), so count out.txt only.
    names = [a["name"] for a in sdk.api.list_artifacts(synced[0])]
    assert names.count("out.txt") == 1
    assert puts.count(b"saved while offline") == 1
    assert not (spool_root() / experiment.id).exists()
    assert sync_all(sdk.api, put=lambda *a, **k: None) == []  # nothing left, nothing duplicated


def test_sync_keeps_the_spool_when_the_server_is_still_down(sdk, tmp_path, monkeypatch):
    experiment = _offline_task(tmp_path, monkeypatch)

    def down(request):
        raise httpx.ConnectError("refused")

    broken = ApiClient(httpx.Client(base_url="http://x", transport=httpx.MockTransport(down)))
    assert sync_all(broken) == []
    assert (spool_root() / experiment.id / "events.jsonl").exists()


def test_sync_completes_a_degraded_online_spool(sdk, tmp_path, monkeypatch):
    exp = sdk.api.create_experiment("vision/seg", "degraded")
    spool = Spool(spool_root() / exp["id"], {"experiment_id": exp["id"]})
    spool.append("metrics", {"points": [{"name": "loss", "value": 1.0, "step": 0, "ts": 1.0}]})
    assert sync_all(sdk.api) == [exp["id"]]
    assert "loss" in sdk.dev.http.get(f"/api/v1/experiments/{exp['id']}/metrics").json()


def test_cli_sync_and_repo_init(sdk, stub_github, tmp_path, monkeypatch):
    _offline_task(tmp_path, monkeypatch)
    monkeypatch.setattr("mlops.transfer.put_file", lambda url, source, http=None: None)
    result = CliRunner().invoke(cli, ["sync"])
    assert result.exit_code == 0 and "synced 1" in result.output
    work, _ = make_repo(tmp_path / "r")
    monkeypatch.chdir(work)
    stub_github.heads[("owner/name", "HEAD")] = "a" * 40
    # dvc missing: init must say so, not crash
    monkeypatch.setattr("mlops.repo.shutil.which", lambda name: None)
    out = CliRunner().invoke(cli, ["repo", "init", "--project", "vision/seg"])
    assert out.exit_code == 1 and "dvc" in out.output


def test_sync_retry_reuses_the_experiment_and_registers_each_artifact_once(
    sdk, tmp_path, monkeypatch
):
    _offline_task(tmp_path, monkeypatch)
    failed: list[str] = []

    def broken_put(url, source, http=None):
        raise httpx.ConnectError("storage down")

    assert sync_all(sdk.api, put=broken_put, failed=failed) == []
    assert failed and "out.txt" in failed[0]  # the error is reported and the spool kept
    synced = sync_all(sdk.api, put=lambda url, source, http=None: None)
    assert len(synced) == 1
    names = [a["name"] for a in sdk.api.list_artifacts(synced[0])]
    assert names.count("out.txt") == 1
    runs = [e for e in sdk.api.list_experiments("vision/seg") if e["name"] == "offline-run"]
    assert [e["id"] for e in runs] == synced


def test_artifact_put_failure_never_reports_the_presigned_url(sdk, tmp_path, monkeypatch):
    _offline_task(tmp_path, monkeypatch)
    urls: list[str] = []

    def forbidden(request):
        return httpx.Response(403, text="signature mismatch")

    client = httpx.Client(transport=httpx.MockTransport(forbidden))

    def put_403(url, source, http=None):
        urls.append(url)
        REAL_PUT(url, source, http=client)

    failed: list[str] = []
    assert sync_all(sdk.api, put=put_403, failed=failed) == []
    assert urls and failed
    query = urls[0].split("?", 1)[1]
    assert "HTTP 403" in failed[0]
    assert urls[0] not in failed[0] and query not in failed[0]


def test_a_spool_that_cannot_be_removed_is_reported_not_silently_kept(sdk, tmp_path, monkeypatch):
    _offline_task(tmp_path, monkeypatch)

    def refuse(path, *args, **kwargs):
        raise PermissionError("read-only spool")

    monkeypatch.setattr("mlops.sync.shutil.rmtree", refuse)
    failed: list[str] = []
    assert sync_all(sdk.api, put=lambda *a, **k: None, failed=failed) == []
    assert any("could not remove the spool" in item for item in failed)
    monkeypatch.undo()
    assert shutil  # the real rmtree is back for the next sync


def test_sync_keeps_the_task_of_an_offline_run(sdk, tmp_path, monkeypatch):
    _offline_task(tmp_path, monkeypatch, task="training", primary_metric="loss", direction="min")
    synced = sync_all(sdk.api, put=lambda url, source, http=None: None)
    assert len(synced) == 1
    assert sdk.api.get_experiment(synced[0])["task"] == "training"
    tasks = {t["name"]: t for t in sdk.api.list_tasks("vision/seg")}
    assert tasks["training"]["primary_metric"] == "loss"


def test_init_repo_reraises_server_errors_other_than_not_installed(
    sdk, stub_github, tmp_path, monkeypatch
):
    work, _ = make_repo(tmp_path)
    stub_github.add_repo("owner/name")

    def server_error(*args, **kwargs):
        request = httpx.Request("POST", "http://x")
        response = httpx.Response(500, json={"detail": "boom"}, request=request)
        response.raise_for_status()

    monkeypatch.setattr(sdk.api, "link_repo", server_error)
    with pytest.raises(httpx.HTTPStatusError):
        init_repo(work, "vision/seg", sdk.api, run=Recorder(), which=lambda name: "/usr/bin/dvc")

from mlops_agent.config import AgentSettings
from mlops_agent.executors.base import RunContext
from mlops_agent.executors.image import ImageExecutor
from mlops_agent.testing.fakes import FakeContainer, FakeDocker
from mlops_common.schemas import JobSpec


def _ctx(tmp_path, spec_extra=None, settings=None):
    spec = JobSpec.model_validate(
        {
            "name": "j",
            "project": "p/q",
            "runtime": {
                "type": "image",
                "image": "alpine:3.20",
                "entrypoint": ["/bin/sh", "-c"],
                "command": ["echo hi"],
            },
            "resources": {"cpu": 1, "memory_gb": 1},
            **(spec_extra or {}),
        }
    )
    out, err = [], []
    root = tmp_path / "job"
    root.mkdir()
    return RunContext(
        "job_2",
        "run_2",
        spec,
        root,
        root,
        {"MLOPS_JOB_ID": "job_2", "X": "1"},
        out.append,
        err.append,
        settings or AgentSettings(home=tmp_path, job_network="mlops"),
    ), out


def test_runs_image_with_entrypoint_command_env_and_network(tmp_path):
    ctx, out = _ctx(tmp_path)
    docker = FakeDocker([FakeContainer(0, ["hi\n"])], images_present=True)
    assert ImageExecutor(docker).run(ctx) == 0 and out == ["hi"]
    run = docker.containers.runs[0]
    assert (
        run["image"] == "alpine:3.20"
        and run["entrypoint"] == ["/bin/sh", "-c"]
        and run["command"] == ["echo hi"]
    )
    assert run["environment"] == {"MLOPS_JOB_ID": "job_2", "X": "1"} and run["network"] == "mlops"
    assert "working_dir" not in run and run["volumes"] == {}
    assert docker.images.pulled == []


def test_missing_image_is_pulled(tmp_path):
    ctx, _ = _ctx(tmp_path)
    docker = FakeDocker([FakeContainer(0)], images_present=False)
    ImageExecutor(docker).run(ctx)
    assert docker.images.pulled == ["alpine:3.20"]


def test_workspace_is_mounted_when_the_job_has_code(tmp_path):
    ctx, _ = _ctx(tmp_path, {"code": {"repo": "o/r", "commit": "a" * 40}})
    docker = FakeDocker([FakeContainer(0)])
    ImageExecutor(docker).run(ctx)
    run = docker.containers.runs[0]
    assert (
        run["volumes"] == {str(ctx.root): {"bind": "/work", "mode": "rw"}}
        and run["working_dir"] == "/work"
    )


def test_registry_login_when_credentials_are_configured(tmp_path):
    docker = FakeDocker([])
    ImageExecutor(docker, AgentSettings(home=tmp_path, dockerhub_user="u", dockerhub_token="t"))
    assert docker.logins == [{"username": "u", "password": "t"}]
    docker2 = FakeDocker([])
    ImageExecutor(docker2, AgentSettings(home=tmp_path))
    assert docker2.logins == []


def test_nonzero_exit_code_is_returned(tmp_path):
    ctx, _ = _ctx(tmp_path)
    assert ImageExecutor(FakeDocker([FakeContainer(7)])).run(ctx) == 7

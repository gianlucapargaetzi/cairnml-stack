import threading

from mlops_agent.config import AgentSettings
from mlops_agent.executors.base import RunContext
from mlops_agent.executors.python import PythonExecutor, venv_volume_name
from mlops_agent.testing.fakes import FakeContainer, FakeDocker
from mlops_common.schemas import JobSpec


def _ctx(tmp_path, runtime=None, resources=None, settings=None, workdir="."):
    spec = JobSpec.model_validate(
        {
            "name": "j",
            "project": "p/q",
            "code": {"repo": "o/r", "commit": "a" * 40, "workdir": workdir},
            "runtime": runtime
            or {
                "type": "python",
                "python": "3.11",
                "requirements": ["numpy==1.26.4"],
                "command": ["python", "train.py", "--lr", "0.1"],
            },
            "resources": resources or {"cpu": 2, "memory_gb": 4},
        }
    )
    out, err = [], []
    root = tmp_path / "job"
    (root / workdir).mkdir(parents=True, exist_ok=True)
    ctx = RunContext(
        "job_1",
        "exp_1",
        spec,
        root,
        (root / workdir).resolve(),
        {"MLOPS_RUN_TOKEN": "t"},
        out.append,
        err.append,
        settings or AgentSettings(home=tmp_path, job_network="mlops"),
    )
    return ctx, out, err


def test_venv_volume_name_depends_on_inputs():
    a = venv_volume_name("3.11", "numpy==1", "mlops-client")
    assert a.startswith("mlops-venv-3.11-") and len(a.split("-")[-1]) == 16
    assert a == venv_volume_name("3.11", "numpy==1", "mlops-client")
    assert a != venv_volume_name("3.11", "numpy==2", "mlops-client")
    assert a != venv_volume_name("3.12", "numpy==1", "mlops-client")


def test_setup_then_run_with_limits_env_and_workdir(tmp_path):
    ctx, out, err = _ctx(tmp_path, workdir="sub")
    docker = FakeDocker(
        [FakeContainer(0, ["installing\n"]), FakeContainer(3, ["epoch 1\n"], ["warn\n"])]
    )
    code = PythonExecutor(docker).run(ctx)
    assert code == 3 and out == ["installing", "epoch 1"] and err == ["warn"]
    setup, main = docker.containers.runs
    assert "venv" in setup["command"][-1] and "/venv/.ready" in setup["command"][-1]
    assert (ctx.root / ".mlops" / "requirements.txt").read_text() == "numpy==1.26.4"
    volume = venv_volume_name("3.11", "numpy==1.26.4", "mlops-client")
    assert setup["volumes"][volume] == {"bind": "/venv", "mode": "rw"}
    assert main["image"] == "python:3.11-slim" and main["command"] == [
        "python",
        "train.py",
        "--lr",
        "0.1",
    ]
    assert main["working_dir"] == "/work/sub" and main["network"] == "mlops"
    assert (
        main["environment"]["PATH"].startswith("/venv/bin:")
        and main["environment"]["MLOPS_RUN_TOKEN"] == "t"
    )
    assert main["nano_cpus"] == 2_000_000_000 and main["mem_limit"] == "4096m"
    assert main["volumes"][str(ctx.root)] == {"bind": "/work", "mode": "rw"}
    assert main["labels"] == {"mlops.job": "job_1"}


def test_failed_setup_skips_the_job_and_containers_are_removed(tmp_path):
    ctx, out, err = _ctx(tmp_path)
    setup = FakeContainer(1, [], ["pip failed\n"])
    docker = FakeDocker([setup])
    assert PythonExecutor(docker).run(ctx) == 1
    assert len(docker.containers.runs) == 1 and setup.removed and err == ["pip failed"]


def test_wheels_dir_is_mounted_for_setup(tmp_path):
    settings = AgentSettings(
        home=tmp_path, wheels_dir=tmp_path / "wheels", client_pip_spec="mlops-client==0.1.0"
    )
    ctx, *_ = _ctx(tmp_path, settings=settings)
    docker = FakeDocker([FakeContainer(0), FakeContainer(0)])
    PythonExecutor(docker).run(ctx)
    setup = docker.containers.runs[0]
    assert setup["volumes"][str(tmp_path / "wheels")] == {"bind": "/wheels", "mode": "ro"}
    assert (
        "--find-links /wheels" in setup["command"][-1]
        and "mlops-client==0.1.0" in setup["command"][-1]
    )


def test_requirements_file_and_default_requirements_txt(tmp_path):
    ctx, *_ = _ctx(
        tmp_path,
        runtime={
            "type": "python",
            "requirements_file": "reqs/dev.txt",
            "command": ["python", "x.py"],
        },
    )
    (ctx.workdir / "reqs").mkdir()
    (ctx.workdir / "reqs" / "dev.txt").write_text("pandas\n")
    PythonExecutor(FakeDocker([FakeContainer(0), FakeContainer(0)])).run(ctx)
    assert (ctx.root / ".mlops" / "requirements.txt").read_text() == "pandas\n"

    ctx2, *_ = _ctx(tmp_path / "other", runtime={"type": "python", "command": ["python", "x.py"]})
    (ctx2.workdir / "requirements.txt").write_text("rich\n")
    PythonExecutor(FakeDocker([FakeContainer(0), FakeContainer(0)])).run(ctx2)
    assert (ctx2.root / ".mlops" / "requirements.txt").read_text() == "rich\n"


def test_cancel_kills_the_running_container(tmp_path):
    ctx, *_ = _ctx(tmp_path)
    block = threading.Event()
    main = FakeContainer(0, block=block)
    executor = PythonExecutor(FakeDocker([FakeContainer(0), main]))
    result = {}
    thread = threading.Thread(target=lambda: result.update(code=executor.run(ctx)))
    thread.start()
    for _ in range(100):
        if executor._container is main:
            break
        threading.Event().wait(0.02)
    executor.cancel()
    thread.join(5)
    assert main.killed and result["code"] == 137 and executor.cancelled and main.removed

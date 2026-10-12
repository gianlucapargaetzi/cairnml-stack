import pytest
from mlops_agent.config import AgentSettings
from mlops_agent.executors.base import RunContext
from mlops_agent.executors.python import PythonExecutor
from mlops_common.schemas import JobSpec

pytestmark = pytest.mark.docker


def test_real_python_job_runs_in_a_venv_and_returns_its_exit_code(tmp_path):
    import docker

    root = tmp_path / "job"
    root.mkdir()
    (root / "train.py").write_text("import sys\nprint('hello from job')\nsys.exit(3)\n")
    spec = JobSpec.model_validate(
        {
            "name": "j",
            "project": "p/q",
            "code": {"repo": "o/r", "commit": "a" * 40},
            "runtime": {"type": "python", "python": "3.11", "command": ["python", "train.py"]},
        }
    )
    out = []
    # `pip` is always installable, so the setup step works without our own wheel
    settings = AgentSettings(home=tmp_path, client_pip_spec="pip")
    ctx = RunContext("job_real", "exp", spec, root, root, {}, out.append, out.append, settings)
    assert PythonExecutor(docker.from_env()).run(ctx) == 3
    assert "hello from job" in out

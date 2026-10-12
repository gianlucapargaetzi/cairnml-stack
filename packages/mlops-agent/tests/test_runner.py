import threading
from datetime import UTC, datetime

from mlops_agent.config import AgentSettings
from mlops_agent.executors.base import BaseExecutor
from mlops_agent.runner import JobRunner
from mlops_agent.testing.helpers import make_origin
from mlops_common.schemas import JobAssignment, JobSpec, StsResponse

STS = StsResponse(
    access_key="AK",
    secret_key="STS-SECRET",
    session_token="STS-SESSION",
    expires_at=datetime(2030, 1, 1, tzinfo=UTC),
    endpoint_url="http://nas",
    bucket="datasets",
    prefix="p/q/",
)


class FakeApi:
    def __init__(self, git_token="GIT-TOKEN-123"):
        self.statuses, self.logs, self.git_token_value = [], [], git_token
        self.artifacts = {}

    def set_status(self, job_id, status, exit_code=None, message=None):
        self.statuses.append((status, exit_code, message))

    def git_token(self, job_id, repo):
        return self.git_token_value

    def run_token(self, job_id):
        return "RUN-TOKEN-456"

    def sts(self, job_id):
        return STS

    def artifact_url(self, job_id, key):
        return f"http://nas/{key}"

    def post_logs(self, experiment_id, stream, seq, lines):
        self.logs.append((stream, [entry["text"] for entry in lines]))


class FakeExecutor(BaseExecutor):
    def __init__(self, code=0, emit=(), raises=None, block=None):
        super().__init__()
        self.code, self.emit, self.raises, self.block, self.ctx = code, emit, raises, block, None

    def _kill(self):
        if self.block:
            self.block.set()

    def run(self, ctx):
        self.ctx = ctx
        for line in self.emit:
            ctx.stdout(line)
        if self.raises:
            raise self.raises
        if self.block:
            self.block.wait(5)
            return 137
        return self.code


def _assignment(web, sha, **overrides):
    spec = {
        "name": "j",
        "project": "p/q",
        "code": {"repo": "owner/name", "commit": sha},
        "runtime": {"type": "python", "command": ["python", "train.py"]},
        "params": {"lr": 0.1},
        "env": {"USER_VAR": "v"},
        **overrides,
    }
    return JobAssignment(job_id="job_9", experiment_id="exp_9", spec=JobSpec.model_validate(spec))


def _runner(tmp_path, api, executor, web, **kw):
    settings = AgentSettings(
        home=tmp_path / "home", server_url="http://mlops-server:8000", git_web_url=web
    )
    return JobRunner(api, settings, lambda kind: executor, **kw), settings


def _logs(api, stream="stdout"):
    return [t for s, texts in api.logs if s == stream for t in texts]


def test_successful_job_pipeline(tmp_path):
    web, sha = make_origin(tmp_path)
    api, executor = FakeApi(), FakeExecutor(emit=["epoch 1"])
    runner, settings = _runner(tmp_path, api, executor, web)
    runner.run(_assignment(web, sha))
    assert [s[0] for s in api.statuses] == ["running", "finished"] and api.statuses[-1][1] == 0
    assert (executor.ctx.root / "train.py").exists() is False  # workspace removed after the run
    assert _logs(api) == ["epoch 1"]
    env = executor.ctx.env
    assert (
        env["MLOPS_RUN_TOKEN"] == "RUN-TOKEN-456"
        and env["MLOPS_SERVER_URL"] == "http://mlops-server:8000"
    )
    assert env["MLOPS_EXPERIMENT_ID"] == "exp_9" and env["MLOPS_JOB_ID"] == "job_9"
    assert env["MLOPS_PARAMS"] == '{"lr": 0.1}' and env["USER_VAR"] == "v"
    assert not settings.paths.work.joinpath("job_9").exists()


def test_user_env_cannot_override_mlops_variables(tmp_path):
    web, sha = make_origin(tmp_path)
    executor = FakeExecutor()
    runner, _ = _runner(tmp_path, FakeApi(), executor, web)
    assignment = _assignment(web, sha)
    assignment.spec.env["MLOPS_RUN_TOKEN"] = "evil"  # bypasses server validation on purpose
    runner.run(assignment)
    assert executor.ctx.env["MLOPS_RUN_TOKEN"] == "RUN-TOKEN-456"


def test_nonzero_exit_is_failed_with_exit_code(tmp_path):
    web, sha = make_origin(tmp_path)
    api = FakeApi()
    runner, _ = _runner(tmp_path, api, FakeExecutor(code=3), web)
    runner.run(_assignment(web, sha))
    assert api.statuses[-1] == ("failed", 3, "exit code 3")


def test_prepare_failure_fails_the_job_and_scrubs_secrets(tmp_path):
    web, sha = make_origin(tmp_path)
    api = FakeApi(git_token="GIT-TOKEN-123")
    runner, _ = _runner(tmp_path, api, FakeExecutor(), web)
    bad = _assignment(web, "f" * 40)  # commit does not exist in the origin
    runner.run(bad)
    status, _, message = api.statuses[-1]
    assert status == "failed" and "GIT-TOKEN-123" not in message
    assert any("fetch" in line or "git" in line for line in _logs(api, "stderr"))
    assert all("GIT-TOKEN-123" not in line for line in _logs(api, "stderr"))


def test_executor_exception_fails_the_job(tmp_path):
    web, sha = make_origin(tmp_path)
    api = FakeApi()
    runner, _ = _runner(
        tmp_path, api, FakeExecutor(raises=RuntimeError("docker exploded RUN-TOKEN-456")), web
    )
    runner.run(_assignment(web, sha))
    status, _, message = api.statuses[-1]
    assert status == "failed" and "RUN-TOKEN-456" not in message and "docker exploded" in message


def test_secrets_are_scrubbed_from_job_output(tmp_path):
    web, sha = make_origin(tmp_path)
    api = FakeApi()
    runner, _ = _runner(tmp_path, api, FakeExecutor(emit=["token is RUN-TOKEN-456 ok"]), web)
    runner.run(_assignment(web, sha))
    assert _logs(api) == ["token is *** ok"]


def test_cancel_during_run_reports_cancelled(tmp_path):
    web, sha = make_origin(tmp_path)
    api = FakeApi()
    block = threading.Event()
    executor = FakeExecutor(block=block)
    runner, _ = _runner(tmp_path, api, executor, web)
    thread = threading.Thread(target=runner.run, args=(_assignment(web, sha),))
    thread.start()
    for _ in range(200):
        if executor.ctx is not None:
            break
        threading.Event().wait(0.02)
    runner.cancel("job_9")
    thread.join(10)
    assert api.statuses[-1][0] == "cancelled"


def test_timeout_fails_the_job(tmp_path):
    web, sha = make_origin(tmp_path)
    api = FakeApi()
    runner, _ = _runner(tmp_path, api, FakeExecutor(block=threading.Event()), web)
    assignment = _assignment(web, sha)
    assignment.spec.timeout_s = 60
    runner._timeout_scale = 0.01  # 60 s becomes 0.6 s in the test
    runner.run(assignment)
    assert api.statuses[-1][0] == "failed" and "timed out" in api.statuses[-1][2]


def test_unsupported_dataset_fails_fast_with_clear_message(tmp_path):
    web, sha = make_origin(tmp_path)
    api = FakeApi()
    runner, _ = _runner(tmp_path, api, FakeExecutor(), web)
    runner.run(_assignment(web, sha, data=[{"path": "d", "repo": "other/repo"}]))
    status, _, message = api.statuses[-1]
    assert status == "failed" and "only datasets in the code repository" in message


def test_datasets_trigger_sts_and_dvc_pull(tmp_path):
    web, sha = make_origin(tmp_path)
    pulled = {}
    runner, _ = _runner(
        tmp_path,
        FakeApi(),
        FakeExecutor(),
        web,
        dvc_pull_fn=lambda workdir, targets, sts: pulled.update(targets=targets, sts=sts),
    )
    runner.run(_assignment(web, sha, data=[{"path": "data/train"}]))
    assert pulled["targets"] == ["data/train"] and pulled["sts"].secret_key == "STS-SECRET"


def test_inputs_are_downloaded_into_the_workspace(tmp_path):
    web, sha = make_origin(tmp_path)
    fetched = []
    runner, _ = _runner(
        tmp_path,
        FakeApi(),
        FakeExecutor(),
        web,
        download_fn=lambda url, dest, *a, **k: fetched.append((url, dest.name)),
    )
    runner.run(_assignment(web, sha, inputs=[{"key": "p/q/exp_1/data.csv", "dest": "in/data.csv"}]))
    assert fetched == [("http://nas/p/q/exp_1/data.csv", "data.csv")]

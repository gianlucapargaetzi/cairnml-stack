import stat

import httpx
import pytest
from mlops_agent.enroll import enroll
from mlops_agent.identity import load_identity
from mlops_common.schemas import Capabilities

CAPS = Capabilities(cpu=4, memory_gb=8)


def _token(enroll_client, queues=("default",)):
    admin = enroll_client("root", roles=["mlops-admin"])
    return admin.http.post("/api/v1/admin/agent-tokens", json={"queues": list(queues)}).json()[
        "token"
    ]


def test_enroll_writes_key_and_identity(server, enroll_client, agent_home):
    identity = enroll(
        agent_home, "http://testserver", _token(enroll_client), "gpu-box", CAPS, http=server
    )
    assert identity.agent_id.startswith("agt_")
    assert stat.S_IMODE(agent_home.key.stat().st_mode) == 0o600
    assert load_identity(agent_home) == identity


def test_enroll_twice_is_refused(server, enroll_client, agent_home):
    enroll(agent_home, "http://testserver", _token(enroll_client), "a", CAPS, http=server)
    with pytest.raises(RuntimeError, match="already enrolled"):
        enroll(agent_home, "http://testserver", _token(enroll_client), "a", CAPS, http=server)


def test_failed_enrollment_leaves_no_key_behind(server, agent_home):
    with pytest.raises(httpx.HTTPStatusError):
        enroll(agent_home, "http://testserver", "mlops_at_bad", "a", CAPS, http=server)
    assert not agent_home.key.exists() and load_identity(agent_home) is None


def test_api_full_job_cycle(server, enroll_client, make_project, new_job, agent_home, api_for):
    dev = enroll_client("dev")
    make_project("vision/seg", members=["dev"])
    identity = enroll(
        agent_home, "http://testserver", _token(enroll_client), "a", CAPS, http=server
    )
    api = api_for(agent_home, identity.agent_id)

    assert api.poll([], wait_s=0) is None
    job = new_job(dev.http)
    assignment = api.poll([], wait_s=0)
    assert assignment.job_id == job["id"] and assignment.spec.code.repo == "org/repo"
    api.set_status(job["id"], "running")
    assert api.run_token(job["id"]).count(".") == 2  # a JWT
    assert api.git_token(job["id"], "org/repo") == "ghs_stub"
    assert api.sts(job["id"]).prefix == "vision/seg/"
    api.post_logs(job["experiment_id"], "stdout", 0, [{"ts": 1.0, "text": "hi"}])
    assert api.heartbeat([job["id"]]) == []
    api.set_status(job["id"], "finished", exit_code=0)
    logs = dev.http.get(f"/api/v1/experiments/{job['experiment_id']}/logs").json()
    assert logs[0]["lines"][0]["text"] == "hi"

import pytest
from mlops_server.models import Agent, Job


def _poll(agent, wait_s=0, running=()):
    body = {"wait_s": wait_s, "running_job_ids": list(running)}
    return agent.http.post("/api/v1/agents/poll", json=body)


@pytest.fixture
def dev(enroll_client, make_project):
    dev = enroll_client("dev")
    make_project("vision/seg", members=["dev"])
    return dev


def test_poll_returns_204_when_nothing_queued(server, make_agent):
    assert _poll(make_agent()).status_code == 204


def test_poll_assigns_fifo_and_marks_job_assigned(server, make_agent, dev, new_job, app):
    agent = make_agent()
    first, second = new_job(dev.http), new_job(dev.http)
    got = _poll(agent).json()
    assert got["job_id"] == first["id"] and got["run_id"] == first["run_id"]
    assert got["spec"]["runtime"]["type"] == "python"
    with app.state.session_factory() as s:
        job = s.get(Job, first["id"])
        assert job.status == "assigned" and job.agent_id == agent.agent_id
        assert s.get(Job, second["id"]).status == "queued"


def test_only_matching_queues_are_served(server, make_agent, dev, new_job):
    gpu_agent = make_agent(queues=["gpu"])
    job = new_job(dev.http, queue="default")
    assert _poll(gpu_agent).status_code == 204
    assert _poll(make_agent(queues=["default"])).json()["job_id"] == job["id"]


def test_resource_matching_skips_jobs_that_do_not_fit(server, make_agent, dev, new_job):
    small = make_agent(cpu=2, memory_gb=4)
    big = new_job(dev.http, resources={"cpu": 8})
    fits = new_job(dev.http, resources={"cpu": 1})
    assert _poll(small).json()["job_id"] == fits["id"]  # skipped the older, larger job
    assert _poll(make_agent(cpu=16)).json()["job_id"] == big["id"]


def test_free_resources_account_for_running_jobs(server, make_agent, dev, new_job):
    agent = make_agent(cpu=4, memory_gb=8)
    new_job(dev.http, resources={"cpu": 3})
    new_job(dev.http, resources={"cpu": 2})
    assert _poll(agent).status_code == 200
    assert _poll(agent).status_code == 204  # 1 cpu left, second job needs 2


def test_labels_gpus_and_runtimes(server, make_agent, dev, new_job):
    plain = make_agent(gpus=0, runtimes=["python"])
    gpu_job = new_job(dev.http, resources={"gpu": 1, "labels": ["a100"]})
    image_job = new_job(dev.http, runtime={"type": "image", "image": "alpine"})
    assert _poll(plain).status_code == 204  # no gpu; image runtime unsupported
    gpu_agent = make_agent(gpus=1, labels=["a100"], runtimes=["python"])
    assert _poll(gpu_agent).json()["job_id"] == gpu_job["id"]
    assert _poll(make_agent(runtimes=["image"])).json()["job_id"] == image_job["id"]


def test_two_agents_never_get_the_same_job(server, make_agent, dev, new_job):
    new_job(dev.http)
    a, b = make_agent(), make_agent()
    codes = sorted([_poll(a).status_code, _poll(b).status_code])
    assert codes == [200, 204]


def test_clients_cannot_poll(server, dev):
    assert dev.http.post("/api/v1/agents/poll", json={"wait_s": 0}).status_code == 403


def test_heartbeat_updates_last_seen_and_requests_cancellation(
    server, make_agent, dev, new_job, app
):
    agent = make_agent()
    job = new_job(dev.http)
    _poll(agent)
    with app.state.session_factory() as s:
        s.get(Job, job["id"]).cancel_requested = True
        s.commit()
    beat = {"running_job_ids": [job["id"], "job_unknown"]}
    body = agent.http.post("/api/v1/agents/heartbeat", json=beat).json()
    assert set(body["cancel_job_ids"]) == {job["id"], "job_unknown"}
    with app.state.session_factory() as s:
        assert s.get(Agent, agent.agent_id).last_seen is not None


def test_jobs_beyond_the_first_page_are_still_offered(server, make_agent, dev, new_job):
    small = make_agent(cpu=4)
    for _ in range(60):
        new_job(dev.http, resources={"cpu": 8})  # never fit this agent
    fitting = new_job(dev.http, resources={"cpu": 1})  # queued behind 60 blockers
    assert _poll(small).json()["job_id"] == fitting["id"]


def test_first_fitting_job_in_fifo_order_is_chosen(server, make_agent, dev, new_job):
    agent = make_agent(cpu=8)
    first = new_job(dev.http, resources={"cpu": 2})
    second = new_job(dev.http, resources={"cpu": 2})
    assert _poll(agent).json()["job_id"] == first["id"]
    assert _poll(agent).json()["job_id"] == second["id"]

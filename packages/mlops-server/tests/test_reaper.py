from datetime import timedelta

from mlops_server.db import utcnow
from mlops_server.models import Agent, Job, Run
from mlops_server.services.reaper import reap_lost_agents


def _running_job(dev, make_agent, new_job):
    agent = make_agent(cpu=2)
    job = new_job(dev.http, resources={"cpu": 2})
    agent.http.post("/api/v1/agents/poll", json={"wait_s": 0})
    agent.http.post(f"/api/v1/jobs/{job['id']}/status", json={"status": "running"})
    return agent, job


def _dev(enroll_client, make_project):
    dev = enroll_client("dev")
    make_project("vision/seg", members=["dev"])
    return dev


def test_job_of_a_silent_agent_is_failed_and_resources_freed(
    server, app, enroll_client, make_project, make_agent, new_job
):
    dev = _dev(enroll_client, make_project)
    agent, job = _running_job(dev, make_agent, new_job)
    with app.state.session_factory() as s:
        s.get(Agent, agent.agent_id).last_seen = utcnow() - timedelta(seconds=300)
        s.commit()
    with app.state.session_factory() as s:
        assert reap_lost_agents(s, utcnow(), 90) == [job["id"]]
        s.commit()
    with app.state.session_factory() as s:
        assert s.get(Job, job["id"]).status == "failed"
        assert s.get(Job, job["id"]).message == "agent lost contact"
        assert s.get(Run, job["run_id"]).status == "failed"
    new = new_job(dev.http, resources={"cpu": 2})
    assert agent.http.post("/api/v1/agents/poll", json={"wait_s": 0}).json()["job_id"] == new["id"]


def test_live_agents_are_left_alone(
    server, app, enroll_client, make_project, make_agent, new_job
):
    dev = _dev(enroll_client, make_project)
    _, job = _running_job(dev, make_agent, new_job)
    with app.state.session_factory() as s:
        assert reap_lost_agents(s, utcnow(), 90) == []
        assert s.get(Job, job["id"]).status == "running"


def test_never_seen_agent_with_assigned_job_is_reaped(
    server, app, enroll_client, make_project, make_agent, new_job
):
    dev = _dev(enroll_client, make_project)
    agent, job = _running_job(dev, make_agent, new_job)
    with app.state.session_factory() as s:
        s.get(Agent, agent.agent_id).last_seen = None
        s.commit()
        assert reap_lost_agents(s, utcnow(), 90) == [job["id"]]


def test_job_finished_by_its_agent_is_not_reaped(
    server, app, enroll_client, make_project, make_agent, new_job
):
    dev = _dev(enroll_client, make_project)
    agent, job = _running_job(dev, make_agent, new_job)
    with app.state.session_factory() as s:
        s.get(Agent, agent.agent_id).last_seen = utcnow() - timedelta(seconds=300)
        s.get(Job, job["id"]).status = "finished"
        s.commit()
    with app.state.session_factory() as s:
        assert reap_lost_agents(s, utcnow(), 90) == []
        s.commit()
    with app.state.session_factory() as s:
        assert s.get(Job, job["id"]).status == "finished"

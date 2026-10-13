from datetime import timedelta

import pytest
from mlops_server.db import utcnow
from mlops_server.models import Agent


@pytest.fixture
def lab(server, enroll_client, make_project, make_agent, new_job):
    dev = enroll_client("dev")
    make_project("vision/seg", members=["dev"])
    agent = make_agent(queues=["default", "gpu"], cpu=8, memory_gb=32, gpus=2, labels=["a100"])
    running = new_job(dev.http, resources={"cpu": 2, "memory_gb": 4}, name="secret-exp")
    agent.http.post("/api/v1/agents/poll", json={"wait_s": 0})
    agent.http.post(f"/api/v1/jobs/{running['id']}/status", json={"status": "running"})
    queued = new_job(dev.http, queue="nobody")
    return dict(dev=dev, agent=agent, running=running, queued=queued)


def test_heartbeat_usage_is_stored_and_shown(lab):
    gpu = {"index": 0, "util_percent": 90.0, "mem_used_gb": 20.0, "mem_total_gb": 40.0}
    usage = {"cpu_percent": 55.5, "mem_used_gb": 10.0, "mem_total_gb": 32.0, "gpus": [gpu]}
    beat = lab["agent"].http.post
    response = beat("/api/v1/agents/heartbeat", json={"running_job_ids": [], "usage": usage})
    assert response.status_code == 200
    agent = lab["dev"].http.get("/api/v1/resources").json()["agents"][0]
    assert agent["usage"]["cpu_percent"] == 55.5 and agent["usage_at"]
    assert agent["usage"]["gpus"][0]["util_percent"] == 90.0
    assert agent["free"]["cpu"] == 6 and agent["online"] is True
    assert agent["capabilities"]["labels"] == ["a100"] and "public_key" not in agent
    bad = {"cpu_percent": "lots", "mem_used_gb": 1, "mem_total_gb": 2}
    response = beat("/api/v1/agents/heartbeat", json={"running_job_ids": [], "usage": bad})
    assert response.status_code == 422


def test_queue_statistics(lab, app):
    from mlops_server.models import Job

    with app.state.session_factory() as s:
        s.get(Job, lab["queued"]["id"]).created_at = utcnow() - timedelta(minutes=5)
        s.commit()
    body = lab["dev"].http.get("/api/v1/resources").json()
    queues = {q["name"]: q for q in body["queues"]}
    default = queues["default"]
    assert (default["running"], default["queued"], default["agents"]) == (1, 0, 1)
    assert queues["gpu"]["agents"] == 1 and queues["gpu"]["oldest_wait_s"] is None
    nobody = queues["nobody"]
    assert (nobody["queued"], nobody["agents"]) == (1, 0)
    assert nobody["oldest_wait_s"] >= 299


def test_offline_agents_do_not_count_as_serving(lab, app):
    with app.state.session_factory() as s:
        for agent in s.query(Agent):
            agent.last_seen = utcnow() - timedelta(hours=1)
        s.commit()
    body = lab["dev"].http.get("/api/v1/resources").json()
    assert body["agents"][0]["online"] is False and all(q["agents"] == 0 for q in body["queues"])


def test_outsiders_see_anonymous_counts_only(lab, enroll_client):
    eve = enroll_client("eve")  # not a member of vision/seg
    response = eve.http.get("/api/v1/resources")
    assert response.status_code == 200
    body = response.json()
    text = response.text
    assert "secret-exp" not in text and "vision/seg" not in text
    assert lab["running"]["id"] not in text
    agent = body["agents"][0]
    assert agent["running_jobs"] == [] and agent["other_running_jobs"] == 1
    queues = {q["name"]: q for q in body["queues"]}
    assert (queues["default"]["running"], queues["default"]["agents"]) == (1, 1)
    assert queues["nobody"]["queued"] == 1


def test_members_see_their_own_running_jobs(lab):
    agent = lab["dev"].http.get("/api/v1/resources").json()["agents"][0]
    assert agent["running_jobs"][0]["run_name"] == "secret-exp"
    assert agent["running_jobs"][0]["project"] == "vision/seg"
    assert agent["other_running_jobs"] == 0


def test_resources_need_a_login(server):
    assert server.get("/api/v1/resources").status_code == 401

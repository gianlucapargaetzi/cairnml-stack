import pytest


@pytest.fixture
def lab(server, enroll_client, make_project, new_job, make_agent):
    alice, bob = enroll_client("alice"), enroll_client("bob")
    make_project("vision/seg", members=["alice"])
    make_project("nlp/chat", members=["bob"])
    agent = make_agent(cpu=8)
    j1 = new_job(alice.http, resources={"cpu": 2})
    agent.http.post("/api/v1/agents/poll", json={"wait_s": 0})
    agent.http.post(f"/api/v1/jobs/{j1['id']}/status", json={"status": "running"})
    j2 = new_job(alice.http)
    return dict(alice=alice, bob=bob, agent=agent, running=j1, queued=j2)


def test_overview_counts_only_the_callers_projects(lab):
    body = lab["alice"].http.get("/api/v1/overview").json()
    assert body["jobs"]["running"] == 1 and body["jobs"]["queued"] == 1
    assert body["runs_running"] == 1 and body["agents"] == {
        "online": 1,
        "total": 1,
    }  # it polled
    assert [p["slug"] for p in body["projects"]] == ["vision/seg"] and body["projects"][0][
        "runs"
    ] == 2
    assert body["projects"][0]["running"] == 1 and len(body["recent"]) == 2
    other = lab["bob"].http.get("/api/v1/overview").json()
    assert other["jobs"] == {} and other["projects"][0]["runs"] == 0


def test_an_agent_that_stopped_heartbeating_is_offline(lab, app):
    from datetime import timedelta

    from mlops_server.db import utcnow
    from mlops_server.models import Agent

    with app.state.session_factory() as s:
        for agent in s.query(Agent):
            agent.last_seen = utcnow() - timedelta(minutes=10)
        s.commit()
    assert lab["alice"].http.get("/api/v1/overview").json()["agents"] == {"online": 0, "total": 1}
    assert lab["alice"].http.get("/api/v1/agents/status").json()[0]["online"] is False


def test_job_list_filters_and_fields(lab):
    http = lab["alice"].http
    jobs = http.get("/api/v1/jobs").json()
    assert [j["status"] for j in jobs] == ["queued", "running"]  # newest first
    running = http.get("/api/v1/jobs", params={"status": "running"}).json()
    assert [j["id"] for j in running] == [lab["running"]["id"]]
    row = running[0]
    assert (
        row["project"] == "vision/seg"
        and row["run_name"] == "job"
        and row["agent_name"] == "agent"
    )
    assert row["cpu"] == 2
    assert http.get("/api/v1/jobs", params={"project": "nlp/chat"}).status_code == 404
    assert lab["bob"].http.get("/api/v1/jobs").json() == []


def test_agent_status_shows_load_without_secrets(lab):
    status = lab["alice"].http.get("/api/v1/agents/status").json()[0]
    assert status["free"] == {"cpu": 6, "memory_gb": 31.0, "gpu": 0}
    assert status["running_jobs"][0]["project"] == "vision/seg" and "public_key" not in status


def test_run_list_search_sort_and_pagination(lab):
    http = lab["alice"].http  # the fixture already created two runs named "job"
    for name in ["zeta", "alpha", "Beta"]:
        http.post("/api/v1/runs", json={"project": "vision/seg", "name": name})
    first = http.get(
        "/api/v1/runs", params={"sort": "created_at", "order": "asc", "limit": 2}
    )
    assert [e["name"] for e in first.json()] == ["job", "job"] and int(
        first.headers["x-total-count"]
    ) == 5
    page2 = http.get(
        "/api/v1/runs",
        params={"sort": "created_at", "order": "asc", "limit": 2, "offset": 2},
    )
    assert [e["name"] for e in page2.json()] == ["zeta", "alpha"]
    assert [e["name"] for e in http.get("/api/v1/runs", params={"q": "ALPH"}).json()] == [
        "alpha"
    ]
    assert http.get("/api/v1/runs", params={"sort": "name"}).status_code == 200
    assert http.get("/api/v1/runs", params={"sort": "owner; drop"}).status_code == 422


def _metrics(http, exp, name, values, offset=0):
    points = [
        {"name": name, "value": v, "step": i + offset, "ts": float(i)} for i, v in enumerate(values)
    ]
    http.post(f"/api/v1/runs/{exp}/metrics", json={"points": points})


def test_compare_returns_summaries_and_downsampled_series(lab):
    http = lab["alice"].http
    a = http.post(
        "/api/v1/runs", json={"project": "vision/seg", "name": "a", "config": {"lr": 0.1}}
    ).json()["id"]
    b = http.post("/api/v1/runs", json={"project": "vision/seg", "name": "b"}).json()["id"]
    _metrics(http, a, "loss", [3.0, 2.0, 1.0])
    _metrics(http, b, "loss", [float(i) for i in range(1200)])
    body = http.get("/api/v1/runs/compare", params={"ids": f"{a},{b}"}).json()["runs"]
    assert [e["name"] for e in body] == ["a", "b"] and body[0]["config"] == {"lr": 0.1}
    small = body[0]["metrics"]["loss"]
    assert (small["count"], small["min"], small["max"], small["last"]) == (3, 1.0, 3.0, 1.0)
    assert small["series"] == [[0, 3.0], [1, 2.0], [2, 1.0]]
    big = body[1]["metrics"]["loss"]
    assert (
        big["count"] == 1200 and len(big["series"]) <= 501 and big["series"][-1] == [1199, 1199.0]
    )
    assert big["series"][0] == [0, 0.0]


def test_compare_series_never_exceeds_500_points_and_keeps_the_last(lab):
    http = lab["alice"].http
    exp = http.post("/api/v1/runs", json={"project": "vision/seg", "name": "wide"}).json()[
        "id"
    ]
    other = http.post(
        "/api/v1/runs", json={"project": "vision/seg", "name": "other"}
    ).json()["id"]
    _metrics(http, exp, "loss", [float(i) for i in range(1000)])
    _metrics(http, other, "loss", [1.0])
    body = http.get("/api/v1/runs/compare", params={"ids": f"{exp},{other}"}).json()[
        "runs"
    ]
    series = body[0]["metrics"]["loss"]["series"]
    assert len(series) == 500 and series[0] == [0, 0.0] and series[-1] == [999, 999.0]


def test_compare_validation_and_access(lab):
    http = lab["alice"].http
    a = http.post("/api/v1/runs", json={"project": "vision/seg", "name": "a"}).json()["id"]
    assert http.get("/api/v1/runs/compare", params={"ids": a}).status_code == 422
    assert (
        http.get("/api/v1/runs/compare", params={"ids": ",".join(["x"] * 11)}).status_code
        == 422
    )
    assert (
        http.get("/api/v1/runs/compare", params={"ids": f"{a},run_missing"}).status_code
        == 404
    )
    assert lab["bob"].http.get(
        "/api/v1/runs/compare", params={"ids": f"{a},{a}"}
    ).status_code in (404, 422)


def test_admin_users_listing(lab, enroll_client):
    admin = enroll_client("root", roles=["mlops-admin"])
    users = {u["username"]: u for u in admin.http.get("/api/v1/admin/users").json()}
    assert users["alice"]["clients_active"] == 1 and users["alice"]["disabled"] is False
    assert lab["alice"].http.get("/api/v1/admin/users").status_code == 403

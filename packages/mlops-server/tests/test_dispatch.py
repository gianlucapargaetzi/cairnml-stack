import pytest


def _setup(enroll_client, make_project):
    dev = enroll_client("dev")
    make_project("vision/seg", members=["dev"])
    return dev


def test_dispatch_creates_job_and_run(
    server, enroll_client, make_project, new_job
):
    dev = _setup(enroll_client, make_project)
    job = new_job(
        dev.http, params={"lr": 0.1},
        resources={"cpu": 4, "memory_gb": 8, "gpu": 1, "labels": ["a100"]},
    )
    assert job["status"] == "queued" and job["queue"] == "default"
    exp = dev.http.get(f"/api/v1/runs/{job['run_id']}").json()
    assert exp["source"] == "job" and exp["status"] == "queued" and exp["job_id"] == job["id"]
    assert exp["git"]["commit"] == "a" * 40 and exp["params"] == {"lr": 0.1}
    assert exp["python_version"] == "3.11" and exp["argv"] == ["python", "train.py"]


def test_non_member_cannot_dispatch(
    server, enroll_client, make_project, new_job, stub_github
):
    _setup(enroll_client, make_project)
    eve = enroll_client("eve")
    stub_github.commits.add(("org/repo", "a" * 40))
    spec = {"name": "j", "project": "vision/seg", "code": {"repo": "org/repo", "commit": "a" * 40},
            "runtime": {"type": "python", "command": ["python", "t.py"]}}
    assert eve.http.post("/api/v1/jobs", json=spec).status_code == 404


def test_commit_must_exist_on_github(server, enroll_client, make_project, stub_github):
    dev = _setup(enroll_client, make_project)
    spec = {"name": "j", "project": "vision/seg", "code": {"repo": "org/repo", "commit": "b" * 40},
            "runtime": {"type": "python", "command": ["python", "t.py"]}}
    response = dev.http.post("/api/v1/jobs", json=spec)
    assert response.status_code == 422 and "push it first" in response.json()["detail"]
    stub_github.inaccessible.add("org/repo")
    assert "not installed" in dev.http.post("/api/v1/jobs", json=spec).json()["detail"]


@pytest.mark.parametrize("code_commit", ["main", "ABCDEF", "a" * 39, "g" * 40])
def test_branch_names_and_short_shas_rejected(server, enroll_client, make_project, code_commit):
    dev = _setup(enroll_client, make_project)
    spec = {"name": "j", "project": "vision/seg",
            "code": {"repo": "org/repo", "commit": code_commit},
            "runtime": {"type": "python", "command": ["python", "t.py"]}}
    assert dev.http.post("/api/v1/jobs", json=spec).status_code == 422


def test_spec_validation_rules(server, enroll_client, make_project):
    dev = _setup(enroll_client, make_project)
    base = {"name": "j", "project": "vision/seg"}
    nothing_to_run = {**base, "runtime": {"type": "python", "command": ["python", "x.py"]}}
    assert dev.http.post("/api/v1/jobs", json=nothing_to_run).status_code == 422
    compose_without_code = {**base, "runtime": {"type": "compose", "service": "app"}}
    assert dev.http.post("/api/v1/jobs", json=compose_without_code).status_code == 422
    reserved_env = {**base, "runtime": {"type": "image", "image": "alpine"},
                    "env": {"MLOPS_RUN_TOKEN": "x"}}
    assert dev.http.post("/api/v1/jobs", json=reserved_env).status_code == 422
    ok_image = {**base,
                "runtime": {"type": "image", "image": "alpine:3.20", "command": ["echo", "hi"]}}
    assert dev.http.post("/api/v1/jobs", json=ok_image).status_code == 200


def test_referenced_artifacts_must_exist_and_belong_to_project(
    server, enroll_client, make_project, stub_github
):
    dev = _setup(enroll_client, make_project)
    created = dev.http.post("/api/v1/runs", json={"project": "vision/seg", "name": "local"})
    exp = created.json()["id"]
    key = f"vision/seg/{exp}/uncommitted.patch"
    stub_github.commits.add(("org/repo", "a" * 40))
    spec = {"name": "j", "project": "vision/seg",
            "code": {"repo": "org/repo", "commit": "a" * 40, "patch_key": key},
            "runtime": {"type": "python", "command": ["python", "t.py"]}}
    assert dev.http.post("/api/v1/jobs", json=spec).status_code == 422  # not registered yet
    dev.http.post(f"/api/v1/runs/{exp}/artifacts",
                  json={"name": "uncommitted.patch", "key": key, "kind": "patch"})
    assert dev.http.post("/api/v1/jobs", json=spec).status_code == 200
    spec["code"]["patch_key"] = "other/project/x/uncommitted.patch"
    assert dev.http.post("/api/v1/jobs", json=spec).status_code == 422


@pytest.mark.parametrize("repo", ["../..", "org/re po", "org/repo\n", "org/..x"])
def test_bad_repo_rejected_before_github(server, enroll_client, make_project, stub_github, repo):
    dev = _setup(enroll_client, make_project)
    code_spec = {"name": "j", "project": "vision/seg",
                 "code": {"repo": repo, "commit": "a" * 40},
                 "runtime": {"type": "python", "command": ["python", "t.py"]}}
    assert dev.http.post("/api/v1/jobs", json=code_spec).status_code == 422
    data_ref = {"path": "d", "repo": repo, "commit": "a" * 40}
    data_spec = {"name": "j", "project": "vision/seg", "data": [data_ref],
                 "runtime": {"type": "image", "image": "alpine"}}
    assert dev.http.post("/api/v1/jobs", json=data_spec).status_code == 422
    assert stub_github.token_calls == []


@pytest.mark.parametrize("dest", ["x\n", "../x", "/abs", "a//b", "a b"])
def test_unsafe_input_dest_rejected(server, enroll_client, make_project, dest):
    dev = _setup(enroll_client, make_project)
    inputs = [{"key": "vision/seg/e/x", "dest": dest}]
    spec = {"name": "j", "project": "vision/seg", "inputs": inputs,
            "runtime": {"type": "python", "command": ["python", "t.py"]}}
    assert dev.http.post("/api/v1/jobs", json=spec).status_code == 422


def test_unsafe_workdir_with_newline_rejected(server, enroll_client, make_project, stub_github):
    dev = _setup(enroll_client, make_project)
    stub_github.commits.add(("org/repo", "a" * 40))
    spec = {"name": "j", "project": "vision/seg",
            "code": {"repo": "org/repo", "commit": "a" * 40, "workdir": "src\n"},
            "runtime": {"type": "python", "command": ["python", "t.py"]}}
    assert dev.http.post("/api/v1/jobs", json=spec).status_code == 422


@pytest.mark.parametrize("env_key", ["MLOPS_RUN_TOKEN", "mlops_x", "Mlops_Y"])
def test_reserved_env_prefix_is_case_insensitive(server, enroll_client, make_project, env_key):
    dev = _setup(enroll_client, make_project)
    spec = {"name": "j", "project": "vision/seg", "runtime": {"type": "image", "image": "alpine"},
            "env": {env_key: "x"}}
    assert dev.http.post("/api/v1/jobs", json=spec).status_code == 422


@pytest.mark.parametrize("resources", [
    {"cpu": 10000}, {"memory_gb": 5000}, {"gpu": 65}, {"labels": ["x"] * 101},
])
def test_resource_upper_bounds(server, enroll_client, make_project, resources):
    dev = _setup(enroll_client, make_project)
    spec = {"name": "j", "project": "vision/seg", "resources": resources,
            "runtime": {"type": "image", "image": "alpine"}}
    assert dev.http.post("/api/v1/jobs", json=spec).status_code == 422


def test_timeout_and_input_list_bounds(server, enroll_client, make_project):
    dev = _setup(enroll_client, make_project)
    base = {"name": "j", "project": "vision/seg", "runtime": {"type": "image", "image": "alpine"}}
    too_long = {**base, "timeout_s": 7 * 86400 + 1}
    assert dev.http.post("/api/v1/jobs", json=too_long).status_code == 422
    many = {**base, "data": [{"path": f"d{i}"} for i in range(101)]}
    assert dev.http.post("/api/v1/jobs", json=many).status_code == 422


def test_dispatch_with_github_unconfigured_returns_503(server, enroll_client, make_project, app):
    dev = _setup(enroll_client, make_project)
    app.state.github = None  # the server runs without a GitHub App
    spec = {"name": "j", "project": "vision/seg", "code": {"repo": "org/repo", "commit": "a" * 40},
            "runtime": {"type": "python", "command": ["python", "t.py"]}}
    response = dev.http.post("/api/v1/jobs", json=spec)
    assert response.status_code == 503 and "not configured" in response.json()["detail"]

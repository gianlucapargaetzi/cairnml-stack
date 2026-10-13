import pytest


@pytest.fixture
def lab(server, enroll_client, make_project, stub_github):
    dev = enroll_client("dev")
    make_project("vision/seg", members=["dev"])
    stub_github.add_repo("org/code", default="main")
    sha = lambda n: f"{n:040x}"  # noqa: E731
    #  c5 (feature) -> c3 ; c4 (main, merge) -> c2, c3 ; c3 -> c1 ; c2 -> c1 ; c1 root
    stub_github.add_commit("org/code", sha(1), message="root", date="2026-01-01T00:00:00Z")
    stub_github.add_commit("org/code", sha(2), [sha(1)], "main work", date="2026-01-02T00:00:00Z")
    stub_github.add_commit(
        "org/code", sha(3), [sha(1)], "feature work", date="2026-01-03T00:00:00Z"
    )
    stub_github.add_commit(
        "org/code", sha(4), [sha(2), sha(3)], "merge feature", date="2026-01-04T00:00:00Z"
    )
    stub_github.add_commit(
        "org/code", sha(5), [sha(3)], "more feature", date="2026-01-05T00:00:00Z"
    )
    stub_github.add_branch("org/code", "main", sha(4))
    stub_github.add_branch("org/code", "feature", sha(5))
    dev.http.post(
        "/api/v1/projects/repos", json={"project": "vision/seg", "repo": "org/code", "role": "code"}
    )
    return dict(dev=dev, sha=sha, gh=stub_github)


def _graph(dev, **params):
    return dev.http.get(
        "/api/v1/projects/graph", params={"project": "vision/seg", "repo": "org/code", **params}
    )


def test_graph_has_branches_commits_and_parents(lab):
    body = _graph(lab["dev"]).json()
    assert body["default_branch"] == "main" and body["head"] == lab["sha"](4)
    assert [(b["name"], b["default"]) for b in body["branches"]] == [
        ("main", True),
        ("feature", False),
    ]
    shas = [c["sha"] for c in body["commits"]]
    assert shas == [lab["sha"](n) for n in (5, 4, 3, 2, 1)]  # newest first, de-duplicated
    merge = next(c for c in body["commits"] if c["sha"] == lab["sha"](4))
    assert (
        merge["parents"] == [lab["sha"](2), lab["sha"](3)] and merge["message"] == "merge feature"
    )


def test_runs_are_attached_to_the_commits_they_ran_on(lab):
    http = lab["dev"].http
    exp = http.post(
        "/api/v1/runs", json={"project": "vision/seg", "name": "e1", "experiment": "training"}
    ).json()
    http.patch(
        f"/api/v1/runs/{exp['id']}",
        json={"git": {"repo": "org/code", "commit": lab["sha"](3), "dirty": False}},
    )
    other = http.post("/api/v1/runs", json={"project": "vision/seg", "name": "e2"}).json()
    http.patch(
        f"/api/v1/runs/{other['id']}",
        json={"git": {"repo": "someone/else", "commit": lab["sha"](3)}},
    )
    runs = _graph(lab["dev"]).json()["runs"]
    assert [e["name"] for e in runs[lab["sha"](3)]] == ["e1"] and runs[lab["sha"](3)][0][
        "experiment"
    ] == "training"
    assert lab["sha"](4) not in runs


def test_unlinked_repositories_and_non_members_get_404(lab, enroll_client):
    assert (
        lab["dev"]
        .http.get("/api/v1/projects/graph", params={"project": "vision/seg", "repo": "org/other"})
        .status_code
        == 404
    )
    assert (
        enroll_client("eve")
        .http.get("/api/v1/projects/graph", params={"project": "vision/seg", "repo": "org/code"})
        .status_code
        == 404
    )


def test_limit_bounds_and_truncation(lab):
    assert _graph(lab["dev"], limit=5).status_code == 422
    assert _graph(lab["dev"], limit=500).status_code == 422
    assert _graph(lab["dev"], limit=10).json()["truncated"] is False


def test_results_are_cached_until_refresh(lab):
    first = len(lab["gh"].calls)
    _graph(lab["dev"])
    after_one = len(lab["gh"].calls)
    _graph(lab["dev"])
    assert len(lab["gh"].calls) == after_one > first
    _graph(lab["dev"], refresh="true")
    assert len(lab["gh"].calls) > after_one


def test_github_not_installed_is_404(lab):
    lab["gh"].inaccessible.add("org/code")
    assert _graph(lab["dev"], refresh="true").status_code == 404

import pytest


@pytest.fixture
def dev(enroll_client, make_project, stub_github):
    dev = enroll_client("dev")
    make_project("vision/seg", members=["dev"])
    stub_github.add_repo("org/code")
    stub_github.add_repo("org/data")
    return dev


def test_link_list_and_unlink(server, dev):
    link = dev.http.post(
        "/api/v1/projects/repos", json={"project": "vision/seg", "repo": "org/code", "role": "code"}
    )
    assert link.status_code == 200 and link.json() == {
        "project": "vision/seg",
        "repo": "org/code",
        "role": "code",
    }
    dev.http.post(
        "/api/v1/projects/repos", json={"project": "vision/seg", "repo": "org/data", "role": "data"}
    )
    dev.http.post(
        "/api/v1/projects/repos", json={"project": "vision/seg", "repo": "org/code", "role": "code"}
    )  # idempotent
    repos = dev.http.get("/api/v1/projects/repos", params={"project": "vision/seg"}).json()
    assert [(r["repo"], r["role"]) for r in repos] == [("org/code", "code"), ("org/data", "data")]
    assert dev.http.delete(
        "/api/v1/projects/repos", params={"project": "vision/seg", "repo": "org/data"}
    ).json() == {"removed": True}
    assert len(dev.http.get("/api/v1/projects/repos", params={"project": "vision/seg"}).json()) == 1


def test_link_validation_and_access(server, dev, enroll_client, stub_github):
    base = {"project": "vision/seg", "repo": "org/code", "role": "code"}
    assert dev.http.post("/api/v1/projects/repos", json={**base, "role": "docs"}).status_code == 422
    assert (
        dev.http.post("/api/v1/projects/repos", json={**base, "repo": "not-a-repo"}).status_code
        == 422
    )
    stub_github.inaccessible.add("org/code")
    refused = dev.http.post("/api/v1/projects/repos", json=base)
    assert refused.status_code == 422 and "not installed" in refused.json()["detail"]
    eve = enroll_client("eve")
    assert (
        eve.http.post("/api/v1/projects/repos", json={**base, "repo": "org/data"}).status_code
        == 404
    )
    assert (
        eve.http.get("/api/v1/projects/repos", params={"project": "vision/seg"}).status_code == 404
    )


def test_history_reads_require_a_linked_repository(server, dev, enroll_client, stub_github):
    stub_github.add_commit("org/code", "a" * 40, message="first")
    stub_github.add_branch("org/code", "main", "a" * 40)
    stub_github.set_file("org/code", "README.md", "hello")
    stub_github.set_file_history("org/code", "README.md", ["a" * 40])
    base = {"project": "vision/seg", "repo": "org/code"}
    # not linked yet: every history route is a 404, even for a project member
    assert dev.http.get("/api/v1/projects/repos/branches", params=base).status_code == 404
    assert (
        dev.http.get("/api/v1/projects/repos/commits", params={**base, "ref": "main"}).status_code
        == 404
    )
    dev.http.post("/api/v1/projects/repos", json={**base, "role": "code"})
    branches = dev.http.get("/api/v1/projects/repos/branches", params=base).json()
    assert branches == [{"name": "main", "sha": "a" * 40}]
    commits = dev.http.get("/api/v1/projects/repos/commits", params={**base, "ref": "main"}).json()
    assert [c["message"] for c in commits] == ["first"]
    assert dev.http.get(
        "/api/v1/projects/repos/file", params={**base, "ref": "main", "path": "README.md"}
    ).json() == {"path": "README.md", "ref": "main", "text": "hello"}
    assert (
        dev.http.get(
            "/api/v1/projects/repos/file", params={**base, "ref": "main", "path": "nope"}
        ).status_code
        == 404
    )
    assert (
        dev.http.get(
            "/api/v1/projects/repos/file-history",
            params={**base, "ref": "main", "path": "README.md"},
        ).json()[0]["sha"]
        == "a" * 40
    )
    # an unlinked repo stays unreadable for the member, and a non-member gets 404 on the project
    stub_github.add_repo("org/other")
    assert (
        dev.http.get(
            "/api/v1/projects/repos/branches", params={"project": "vision/seg", "repo": "org/other"}
        ).status_code
        == 404
    )
    eve = enroll_client("eve")
    assert eve.http.get("/api/v1/projects/repos/branches", params=base).status_code == 404


def test_history_reads_are_cached_and_map_github_errors(server, dev, stub_github):
    stub_github.add_repo("org/code")
    dev.http.post(
        "/api/v1/projects/repos", json={"project": "vision/seg", "repo": "org/code", "role": "code"}
    )
    params = {"project": "vision/seg", "repo": "org/code"}
    assert dev.http.get("/api/v1/projects/repos/branches", params=params).json() == []
    stub_github.add_branch("org/code", "dev", "b" * 40)
    assert (
        dev.http.get("/api/v1/projects/repos/branches", params=params).json() == []
    )  # served from the 60 s cache
    stub_github.inaccessible.add("org/code")
    assert (
        dev.http.get("/api/v1/projects/repos/branches", params=params).json() == []
    )  # still cached
    # a key not yet cached reaches GitHub and the inaccessible repo maps to 404
    assert (
        dev.http.get("/api/v1/projects/repos/commits", params={**params, "ref": "zzz"}).status_code
        == 404
    )

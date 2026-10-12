import base64

import pytest
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from mlops_server.services.cache import TtlCache
from mlops_server.services.github import GitHubApp, GitHubError

API = "https://ghe.test/api/v3"


@pytest.fixture
def gh():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    with respx.mock:
        respx.get(f"{API}/repos/org/repo/installation").respond(200, json={"id": 1})
        respx.post(f"{API}/app/installations/1/access_tokens").respond(
            201, json={"token": "t", "expires_at": "2030-01-01T00:00:00Z"}
        )
        yield GitHubApp("1", pem, API)


def _commit(sha, parents=(), message="msg\n\nbody", name="Ann", date="2026-01-02T03:04:05Z"):
    return {
        "sha": sha,
        "parents": [{"sha": p} for p in parents],
        "commit": {"message": message, "author": {"name": name, "date": date}},
    }


def test_default_branch_and_branches(gh):
    respx.get(f"{API}/repos/org/repo").respond(200, json={"default_branch": "develop"})
    respx.get(f"{API}/repos/org/repo/branches").respond(
        200,
        json=[
            {"name": "develop", "commit": {"sha": "a" * 40}},
            {"name": "x", "commit": {"sha": "b" * 40}},
        ],
    )
    assert gh.get_default_branch("org/repo") == "develop"
    assert [(b.name, b.sha) for b in gh.list_branches("org/repo")] == [
        ("develop", "a" * 40),
        ("x", "b" * 40),
    ]


def test_commits_parse_parents_and_first_message_line(gh):
    route = respx.get(f"{API}/repos/org/repo/commits").respond(
        200, json=[_commit("c" * 40, ["d" * 40, "e" * 40])]
    )
    commit = gh.list_commits("org/repo", "main", limit=5)[0]
    assert (
        commit.parents == ("d" * 40, "e" * 40)
        and commit.message == "msg"
        and commit.author == "Ann"
    )
    assert route.calls[0].request.url.params["sha"] == "main"
    assert route.calls[0].request.url.params["per_page"] == "5"
    assert gh.list_commits("org/repo", "main")[0].date == "2026-01-02T03:04:05Z"


def test_tree_and_files(gh):
    respx.get(f"{API}/repos/org/repo/git/trees/main").respond(
        200,
        json={
            "truncated": True,
            "tree": [
                {"path": "data/train.dvc", "type": "blob"},
                {"path": "data", "type": "tree"},
            ],
        },
    )
    assert gh.list_tree("org/repo", "main") == (["data/train.dvc"], True)
    text = base64.b64encode(b"hello").decode()
    respx.get(f"{API}/repos/org/repo/contents/data/train.dvc").respond(
        200, json={"encoding": "base64", "content": text + "\n", "size": 5}
    )
    respx.get(f"{API}/repos/org/repo/contents/missing").respond(404)
    respx.get(f"{API}/repos/org/repo/contents/big").respond(
        200, json={"encoding": "none", "content": "", "size": 5_000_000}
    )
    assert gh.read_file("org/repo", "data/train.dvc", "main") == "hello"
    assert gh.read_file("org/repo", "missing", "main") is None
    assert gh.read_file("org/repo", "big", "main") is None  # too large to read


def test_path_history(gh):
    route = respx.get(f"{API}/repos/org/repo/commits").respond(200, json=[_commit("1" * 40)])
    assert [c.sha for c in gh.list_path_commits("org/repo", "data/train.dvc", "main", limit=3)] == [
        "1" * 40
    ]
    assert route.calls[0].request.url.params["path"] == "data/train.dvc"


def test_ref_with_slash_is_percent_encoded_in_the_tree_path(gh):
    route = respx.get(url__startswith=f"{API}/repos/org/repo/git/trees/").respond(
        200, json={"tree": [], "truncated": False}
    )
    gh.list_tree("org/repo", "feature/x")
    assert (
        route.calls[0].request.url.raw_path.decode()
        == "/api/v3/repos/org/repo/git/trees/feature%2Fx?recursive=1"
    )


def test_file_path_is_encoded_per_segment(gh):
    route = respx.get(url__startswith=f"{API}/repos/org/repo/contents/").respond(404)
    gh.read_file("org/repo", "dir with space/a?b.txt", "feature/x")
    raw = route.calls[0].request.url.raw_path.decode()
    assert raw.startswith("/api/v3/repos/org/repo/contents/dir%20with%20space/a%3Fb.txt?")
    assert route.calls[0].request.url.params["ref"] == "feature/x"


def test_unexpected_status_raises_github_error(gh):
    respx.get(f"{API}/repos/org/repo/branches").respond(500)
    with pytest.raises(GitHubError):
        gh.list_branches("org/repo")


def test_cache_serves_repeated_reads_until_ttl_expires():
    now = [0.0]
    cache = TtlCache(60, clock=lambda: now[0])
    calls = []

    def factory():
        calls.append(1)
        return len(calls)

    assert cache.get_or_set("k", factory) == 1
    assert cache.get_or_set("k", factory) == 1
    now[0] = 61
    assert cache.get_or_set("k", factory) == 2
    cache.clear()
    assert cache.get_or_set("k", factory) == 3

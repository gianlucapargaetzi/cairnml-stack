import json
from calendar import timegm

import jwt
import pytest
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from mlops_server.services.github import GitHubApp, RepoNotAccessible, valid_repo

API = "https://ghe.test/api/v3"


@pytest.fixture
def app_key():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    return key.public_key(), pem


@pytest.mark.parametrize("repo,ok", [("org/repo", True), ("a.b/c-d_e", True), ("org", False),
                                      ("a/b/c", False), ("../x", False), ("org/re po", False)])
def test_valid_repo(repo, ok):
    assert valid_repo(repo) is ok


def _mock_install(router, repo="org/repo", expires="2030-01-01T00:00:00Z", token="ghs_1"):
    router.get(f"{API}/repos/{repo}/installation").respond(200, json={"id": 77})
    return router.post(f"{API}/app/installations/77/access_tokens").respond(
        201, json={"token": token, "expires_at": expires})


@respx.mock
def test_installation_token_is_read_only_scoped_and_signed_as_app(app_key):
    public, pem = app_key
    tokens = _mock_install(respx.mock)
    gh = GitHubApp("123", pem, API)
    token = gh.installation_token("org/repo")
    assert token.token == "ghs_1"
    sent = tokens.calls[0].request
    assert json.loads(sent.content) == {
        "repositories": ["repo"],
        "permissions": {"contents": "read"},
    }
    claims = jwt.decode(sent.headers["authorization"].removeprefix("Bearer "), public,
                        algorithms=["RS256"])
    assert claims["iss"] == "123" and claims["exp"] - claims["iat"] <= 600


@respx.mock
def test_installation_token_is_cached_until_near_expiry(app_key):
    _, pem = app_key
    tokens = _mock_install(respx.mock, expires="2030-01-01T00:00:00Z")
    clock = {"now": timegm((2029, 12, 31, 0, 0, 0))}
    gh = GitHubApp("123", pem, API, clock=lambda: clock["now"])
    gh.installation_token("org/repo")
    gh.installation_token("org/repo")
    assert tokens.call_count == 1
    clock["now"] = timegm((2030, 1, 1, 0, 0, 0)) - 60  # inside the 5 min margin
    gh.installation_token("org/repo")
    assert tokens.call_count == 2


@respx.mock
def test_not_installed_raises(app_key):
    _, pem = app_key
    respx.get(f"{API}/repos/org/repo/installation").respond(404)
    with pytest.raises(RepoNotAccessible):
        GitHubApp("123", pem, API).installation_token("org/repo")


@respx.mock
def test_commit_exists_and_head(app_key):
    _, pem = app_key
    _mock_install(respx.mock)
    respx.get(f"{API}/repos/org/repo/commits/{'a' * 40}").respond(200, json={"sha": "a" * 40})
    respx.get(f"{API}/repos/org/repo/commits/{'b' * 40}").respond(422, json={})
    respx.get(f"{API}/repos/org/repo/commits/main").respond(200, json={"sha": "c" * 40})
    respx.get(f"{API}/repos/org/repo/commits/nope").respond(404)
    gh = GitHubApp("123", pem, API)
    assert gh.commit_exists("org/repo", "a" * 40) is True
    assert gh.commit_exists("org/repo", "b" * 40) is False
    assert gh.head_commit("org/repo", "main") == "c" * 40
    assert gh.head_commit("org/repo", "nope") is None


def test_repos_status_endpoint(server, enroll_client, stub_github):
    stub_github.heads[("org/repo", "main")] = "d" * 40
    dev = enroll_client("dev")
    ok = dev.http.get("/api/v1/repos/status", params={"repo": "org/repo", "ref": "main"})
    assert ok.json() == {"repo": "org/repo", "ref": "main", "head": "d" * 40}
    bad = dev.http.get("/api/v1/repos/status", params={"repo": "bad", "ref": "main"})
    assert bad.status_code == 422
    stub_github.inaccessible.add("org/secret")
    secret = dev.http.get("/api/v1/repos/status", params={"repo": "org/secret", "ref": "main"})
    assert secret.status_code == 404

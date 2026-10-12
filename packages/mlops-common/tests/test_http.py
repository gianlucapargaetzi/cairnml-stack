import json

import httpx
from mlops_common.assertion import verify_assertion
from mlops_common.http import KeyAuth, StaticTokenAuth, make_client
from mlops_common.keys import generate_private_key

URL = "http://mlops-server:8000"


class FakeServer:
    """Issues tokens t1, t2, ... in order and accepts only the most recently issued one."""

    def __init__(self) -> None:
        self.issued: list[str] = []
        self.assertions: list[str] = []
        self.auth_headers: list[str | None] = []

    def rotate(self) -> str:
        """Issue a new token out of band, invalidating the previous one."""
        token = f"t{len(self.issued) + 1}"
        self.issued.append(token)
        return token

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/auth/token":
            self.assertions.append(json.loads(request.read())["assertion"])
            self.rotate()
            return httpx.Response(200, json={"access_token": self.issued[-1], "expires_in": 3600})
        header = request.headers.get("authorization")
        self.auth_headers.append(header)
        accepted = bool(self.issued) and header == f"Bearer {self.issued[-1]}"
        return httpx.Response(200 if accepted else 401)


def _client(server: FakeServer, key) -> httpx.Client:
    transport = httpx.MockTransport(server.handler)
    auth = KeyAuth(URL, "cli_x", key, token_client=httpx.Client(transport=transport, base_url=URL))
    return make_client(URL, auth=auth, transport=transport)


def test_fetches_token_lazily_signs_assertion_and_caches():
    key = generate_private_key()
    server = FakeServer()
    client = _client(server, key)
    assert not server.assertions  # lazy
    assert client.get("/ping").status_code == 200
    assert client.get("/ping").status_code == 200
    assert len(server.assertions) == 1  # cached
    claims = verify_assertion(server.assertions[0], key.public_key(), URL)
    assert claims["iss"] == "cli_x"


def test_refreshes_once_on_401():
    key = generate_private_key()
    server = FakeServer()
    client = _client(server, key)
    assert client.get("/ping").status_code == 200  # uses t1
    server.rotate()  # server now accepts only t2; the cached t1 is stale
    resp = client.get("/ping")
    assert resp.status_code == 200
    assert server.auth_headers == ["Bearer t1", "Bearer t1", "Bearer t3"]
    assert len(server.assertions) == 2  # one initial fetch, one refresh on 401


def test_static_token_auth():
    seen = []

    def handler(request):
        seen.append(request.headers["authorization"])
        return httpx.Response(200)

    client = make_client(
        URL, auth=StaticTokenAuth("run-token"), transport=httpx.MockTransport(handler)
    )
    client.get("/x")
    assert seen == ["Bearer run-token"]

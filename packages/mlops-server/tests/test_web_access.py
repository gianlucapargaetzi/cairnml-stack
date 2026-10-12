import pytest
from mlops_server.testing import login_browser


@pytest.fixture
def seeded(server, enroll_client, make_project, new_job, make_agent):
    dev = enroll_client("alice")
    make_project("vision/seg", members=["alice"])
    agent = make_agent()
    job = new_job(dev.http)
    exp = dev.http.post("/api/v1/experiments", json={"project": "vision/seg", "name": "n"}).json()
    return dict(dev=dev, job=job, exp=exp["id"], agent=agent)


READS = ["/api/v1/projects", "/api/v1/experiments", "/api/v1/experiments/{exp}",
         "/api/v1/experiments/{exp}/metrics", "/api/v1/experiments/{exp}/logs",
         "/api/v1/experiments/{exp}/artifacts", "/api/v1/jobs/{job}"]


@pytest.mark.parametrize("path", READS)
def test_a_logged_in_browser_can_read(browser, seeded, path):
    login_browser(browser)  # the fake IdP user is "alice", a member of the project
    response = browser.get(path.format(exp=seeded["exp"], job=seeded["job"]["id"]))
    assert response.status_code == 200, (path, response.text)


def test_a_browser_only_sees_what_its_user_may_see(browser, seeded):
    browser.idp["username"] = "mallory"
    login_browser(browser)
    assert browser.get("/api/v1/projects").json() == []
    assert browser.get(f"/api/v1/experiments/{seeded['exp']}").status_code == 404
    assert browser.get(f"/api/v1/jobs/{seeded['job']['id']}").status_code == 404


WRITES = [
    ("post", "/api/v1/experiments", {"project": "vision/seg", "name": "x"}),
    ("patch", "/api/v1/experiments/{exp}", {"notes": "x"}),
    ("post", "/api/v1/experiments/{exp}/metrics", {"points": [{"name": "a", "value": 1, "ts": 1}]}),
    ("post", "/api/v1/experiments/{exp}/logs",
     {"stream": "stdout", "seq": 0, "lines": [{"ts": 1, "text": "x"}]}),
    ("post", "/api/v1/experiments/{exp}/artifacts/presign", {"name": "a"}),
    ("post", "/api/v1/storage/sts", {"project": "vision/seg"}),
    ("post", "/api/v1/projects", {"slug": "a", "name": "a"}),
    ("post", "/api/v1/admin/agent-tokens", {}),
    ("post", "/api/v1/admin/sync-users", None),
    ("post", "/api/v1/agents/poll", {"wait_s": 0}),
]


@pytest.mark.parametrize("method,path,body", WRITES)
def test_a_browser_session_can_change_nothing(browser, seeded, method, path, body):
    login_browser(browser)
    response = getattr(browser, method)(path.format(exp=seeded["exp"], job=seeded["job"]["id"]),
                                        **({"json": body} if body is not None else {}))
    assert response.status_code in (403, 404), (path, response.status_code)
    after = seeded["dev"].http.get(f"/api/v1/experiments/{seeded['exp']}").json()
    assert after["notes"] is None


def test_admin_listings_for_a_web_admin(browser, seeded):
    browser.idp["username"], browser.idp["roles"] = "root", ["mlops-admin"]
    login_browser(browser)
    assert browser.get("/api/v1/admin/agents").status_code == 200
    assert browser.get("/api/v1/admin/clients").status_code == 200
    browser.cookies.clear()
    browser.idp["username"], browser.idp["roles"] = "alice", []
    login_browser(browser)
    assert browser.get("/api/v1/admin/agents").status_code == 403


def test_security_headers(server):
    api = server.get("/api/v1/healthz")
    assert api.headers["x-content-type-options"] == "nosniff"
    assert api.headers["referrer-policy"] == "same-origin"
    assert api.headers["x-frame-options"] == "DENY" and api.headers["cache-control"] == "no-store"
    assert "content-security-policy" not in api.headers
    ui = server.get("/ui/auth/login", follow_redirects=False)
    assert "default-src 'self'" in ui.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in ui.headers["content-security-policy"]

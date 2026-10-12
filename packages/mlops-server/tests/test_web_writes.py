import pytest
from mlops_server.testing import login_browser


@pytest.fixture
def lab(server, enroll_client, make_project, new_job):
    alice = enroll_client("alice")
    make_project("vision/seg", members=["alice"])
    return dict(
        alice=alice,
        job=new_job(alice.http),
        exp=alice.http.post(
            "/api/v1/experiments", json={"project": "vision/seg", "name": "x", "task": "training"}
        ).json(),
    )


def _task_id(lab):
    return next(
        t
        for t in lab["alice"].http.get("/api/v1/tasks", params={"project": "vision/seg"}).json()
        if t["name"] == "training"
    )["id"]


def test_a_browser_can_cancel_a_job_with_the_csrf_token(browser, lab):
    me = login_browser(browser)
    url = f"/api/v1/jobs/{lab['job']['id']}/cancel"
    assert browser.post(url).status_code == 403
    assert browser.post(url, headers={"X-CSRF-Token": "wrong"}).status_code == 403
    assert (
        browser.post(
            url, headers={"X-CSRF-Token": me["csrf"], "Origin": "http://evil.example"}
        ).status_code
        == 403
    )
    assert lab["alice"].http.get(f"/api/v1/jobs/{lab['job']['id']}").json()["status"] == "queued"
    ok = browser.post(url, headers={"X-CSRF-Token": me["csrf"], "Origin": "http://testserver"})
    assert ok.status_code == 200 and ok.json()["status"] == "cancelled"


def test_a_browser_without_an_origin_header_still_needs_the_token(browser, lab):
    me = login_browser(browser)
    ok = browser.post(
        f"/api/v1/jobs/{lab['job']['id']}/cancel", headers={"X-CSRF-Token": me["csrf"]}
    )
    assert ok.status_code == 200


def test_a_browser_can_edit_a_task(browser, lab):
    me = login_browser(browser)
    url = f"/api/v1/tasks/{_task_id(lab)}"
    assert browser.patch(url, json={"description": "x"}).status_code == 403
    done = browser.patch(
        url,
        json={"description": "fine-tune", "primary_metric": "val_loss", "direction": "min"},
        headers={"X-CSRF-Token": me["csrf"]},
    )
    assert done.status_code == 200 and done.json()["primary_metric"] == "val_loss"


def test_other_users_projects_stay_untouchable(browser, lab, enroll_client, make_project):
    enroll_client("mallory")
    browser.idp["username"] = "mallory"
    me = login_browser(browser)
    assert (
        browser.post(
            f"/api/v1/jobs/{lab['job']['id']}/cancel", headers={"X-CSRF-Token": me["csrf"]}
        ).status_code
        == 404
    )
    assert (
        browser.patch(
            f"/api/v1/tasks/{_task_id(lab)}",
            json={"description": "x"},
            headers={"X-CSRF-Token": me["csrf"]},
        ).status_code
        == 404
    )


@pytest.mark.parametrize(
    "method,path,body",
    [
        (
            "post",
            "/api/v1/jobs",
            {"name": "x", "project": "vision/seg", "runtime": {"type": "image", "image": "a"}},
        ),
        ("post", "/api/v1/experiments", {"project": "vision/seg", "name": "x"}),
        ("patch", "/api/v1/experiments/{exp}", {"notes": "x"}),
        ("post", "/api/v1/tasks", {"project": "vision/seg", "name": "new"}),
        ("post", "/api/v1/storage/sts", {"project": "vision/seg"}),
        ("post", "/api/v1/admin/sync-users", None),
    ],
)
def test_every_other_write_is_still_denied_even_with_a_valid_token(
    browser, lab, method, path, body
):
    me = login_browser(browser)
    response = getattr(browser, method)(
        path.format(exp=lab["exp"]["id"]),
        headers={"X-CSRF-Token": me["csrf"]},
        **({"json": body} if body is not None else {}),
    )
    assert response.status_code in (403, 404, 422) and response.status_code != 200


def test_browser_writes_are_audited_with_the_users_id(browser, lab, app):
    from mlops_server.models import AuditEvent
    from sqlalchemy import select

    me = login_browser(browser)
    browser.post(f"/api/v1/jobs/{lab['job']['id']}/cancel", headers={"X-CSRF-Token": me["csrf"]})
    with app.state.session_factory() as s:
        event = s.scalar(select(AuditEvent).where(AuditEvent.action == "job.cancel_requested"))
        assert event.actor.startswith("usr_")

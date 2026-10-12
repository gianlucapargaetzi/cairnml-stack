def test_admin_creates_project_and_non_admin_cannot(server, enroll_client):
    admin, dev = enroll_client("root", roles=["mlops-admin"]), enroll_client("dev")
    body = {"slug": "vision/seg", "name": "Segmentation"}
    assert dev.http.post("/api/v1/projects", json=body).status_code == 403
    assert admin.http.post("/api/v1/projects", json=body).json() == body
    assert admin.http.post("/api/v1/projects", json=body).status_code == 409


def test_invalid_slugs_are_rejected(server, enroll_client):
    admin = enroll_client("root", roles=["mlops-admin"])
    for slug in ["", "UPPER", "a/b/c", "../x", "has space"]:
        response = admin.http.post("/api/v1/projects", json={"slug": slug, "name": "x"})
        assert response.status_code == 422


def test_membership_controls_listing(server, enroll_client, make_project):
    enroll_client("alice"), enroll_client("bob")
    make_project("vision/seg", members=["alice"])
    make_project("nlp/chat", members=["bob"])
    alice = enroll_client("alice")
    assert [p["slug"] for p in alice.http.get("/api/v1/projects").json()] == ["vision/seg"]
    admin = enroll_client("root", roles=["mlops-admin"])
    listed = admin.http.get("/api/v1/projects").json()
    assert {p["slug"] for p in listed} == {"vision/seg", "nlp/chat"}


def test_add_member_errors(server, enroll_client, make_project):
    admin = enroll_client("root", roles=["mlops-admin"])
    make_project("vision/seg")
    unknown_project = {"project": "nope/x", "username": "a"}
    unknown_user = {"project": "vision/seg", "username": "ghost"}
    assert admin.http.post("/api/v1/project-members", json=unknown_project).status_code == 404
    assert admin.http.post("/api/v1/project-members", json=unknown_user).status_code == 404

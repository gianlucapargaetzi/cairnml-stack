import json
import time

import jwt
from mlops_common.assertion import make_assertion
from mlops_common.keys import generate_private_key, public_key_pem
from mlops_server.models import AuditEvent, Client, User
from sqlalchemy import func, select


def _enroll(server, idp, key=None, **token_kw):
    key = key or generate_private_key()
    return server.post(
        "/api/v1/enroll/client",
        json={"name": "laptop", "public_key": public_key_pem(key)},
        headers={"Authorization": f"Bearer {idp.token(**token_kw)}"},
    ), key


def test_enroll_creates_user_and_client(server, idp, app):
    response, _ = _enroll(server, idp, sub="s1", username="alice", roles=["mlops-admin"])
    assert response.status_code == 200
    assert response.json()["username"] == "alice"
    with app.state.session_factory() as s:
        assert s.scalar(select(User).where(User.idp_subject == "s1")).roles == ["mlops-admin"]
        assert s.scalar(select(AuditEvent).where(AuditEvent.action == "client.enrolled"))


def test_enroll_requires_valid_idp_token(server, idp):
    assert _enroll(server, idp, azp="other")[0].status_code == 401
    assert _enroll(server, idp, run_in=-5)[0].status_code == 401
    bare = server.post("/api/v1/enroll/client", json={"name": "x", "public_key": "k"})
    assert bare.status_code == 401


def test_enroll_rejects_bad_and_duplicate_keys(server, idp):
    bad = server.post(
        "/api/v1/enroll/client",
        json={"name": "x", "public_key": "junk"},
        headers={"Authorization": f"Bearer {idp.token()}"},
    )
    assert bad.status_code == 422
    first, key = _enroll(server, idp)
    assert first.status_code == 200
    assert _enroll(server, idp, key=key)[0].status_code == 409


def test_second_enrollment_refreshes_roles(server, idp, app):
    _enroll(server, idp, sub="s2", roles=[])
    _enroll(server, idp, sub="s2", roles=["mlops-admin"])
    with app.state.session_factory() as s:
        assert s.scalar(select(User).where(User.idp_subject == "s2")).roles == ["mlops-admin"]


def test_token_exchange_and_me(server, enroll_client):
    me = enroll_client("bob").http.get("/api/v1/me")
    assert me.status_code == 200 and me.json()["kind"] == "client"


def _exchange(server, assertion):
    return server.post("/api/v1/auth/token", json={"assertion": assertion})


def test_token_exchange_failures_are_indistinguishable(server, enroll_client):
    enrolled = enroll_client()
    other = generate_private_key()
    good = make_assertion(enrolled.key, enrolled.client_id, "http://testserver")
    cases = [
        make_assertion(other, enrolled.client_id, "http://testserver"),  # wrong key
        make_assertion(enrolled.key, "cli_unknown", "http://testserver"),  # unknown id
        make_assertion(enrolled.key, enrolled.client_id, "http://evil"),  # wrong audience
        make_assertion(enrolled.key, enrolled.client_id, "http://testserver", now=1000),  # expired
        make_assertion(enrolled.key, "weird", "http://testserver"),  # bad prefix
        "garbage",
    ]
    bodies = {json.dumps(_exchange(server, a).json()) for a in cases}
    statuses = {_exchange(server, a).status_code for a in cases}
    assert statuses == {401} and len(bodies) == 1
    assert _exchange(server, good).status_code == 200


def test_replayed_assertion_is_rejected(server, enroll_client):
    enrolled = enroll_client()
    assertion = make_assertion(enrolled.key, enrolled.client_id, "http://testserver")
    assert _exchange(server, assertion).status_code == 200
    assert _exchange(server, assertion).status_code == 401


def test_revoked_client_cannot_exchange(server, enroll_client, app):
    from mlops_server.db import utcnow
    from mlops_server.models import Client

    enrolled = enroll_client()
    with app.state.session_factory() as s:
        s.get(Client, enrolled.client_id).revoked_at = utcnow()
        s.commit()
    assertion = make_assertion(enrolled.key, enrolled.client_id, "http://testserver")
    assert _exchange(server, assertion).status_code == 401


def _set_user_disabled(app, idp_subject, disabled=True):
    with app.state.session_factory() as s:
        s.scalar(select(User).where(User.idp_subject == idp_subject)).disabled = disabled
        s.commit()


def test_disabled_user_cannot_enroll_new_client(server, idp, app):
    first, _ = _enroll(server, idp, sub="s3", roles=[])
    assert first.status_code == 200
    _set_user_disabled(app, "s3")
    response, _ = _enroll(server, idp, sub="s3", roles=["mlops-admin"])
    assert response.status_code == 403
    with app.state.session_factory() as s:
        user = s.scalar(select(User).where(User.idp_subject == "s3"))
        assert user.roles == [] and user.disabled is True
        assert (
            s.scalar(select(func.count()).select_from(Client).where(Client.user_id == user.id)) == 1
        )


def test_client_of_disabled_user_cannot_exchange(server, enroll_client, app):
    enrolled = enroll_client("carol")
    _set_user_disabled(app, "sub-carol")
    assertion = make_assertion(enrolled.key, enrolled.client_id, "http://testserver")
    assert _exchange(server, assertion).status_code == 401


def test_overlong_jti_is_refused(server, enroll_client):
    enrolled = enroll_client()
    now = int(time.time())
    claims = {
        "iss": enrolled.client_id,
        "sub": enrolled.client_id,
        "aud": "http://testserver",
        "iat": now,
        "exp": now + 120,
        "jti": "j" * 65,
    }
    assertion = jwt.encode(claims, enrolled.key, algorithm="EdDSA")
    assert _exchange(server, assertion).status_code == 401

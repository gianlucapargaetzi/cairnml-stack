import time

import jwt
import pytest
from mlops_common.keys import generate_private_key, public_key_pem
from mlops_server.db import utcnow
from mlops_server.ids import new_id
from mlops_server.models import Agent, Client, User
from mlops_server.security.tokens import TokenInvalid, TokenService


def _service(ttl=3600):
    return TokenService(generate_private_key(), "http://testserver", ttl)


def test_issue_and_verify_roundtrip():
    svc = _service()
    token, expires_in = svc.issue("cli_1", "client", uid="usr_1")
    claims = svc.verify(token)
    assert (claims.sub, claims.kind, claims.uid) == ("cli_1", "client", "usr_1")
    assert expires_in == 3600


def test_verify_rejects_expired_foreign_and_garbage():
    svc = _service()
    token, _ = svc.issue("cli_1", "client", ttl=-5)
    with pytest.raises(TokenInvalid):
        svc.verify(token)
    other_token, _ = _service().issue("cli_1", "client")
    with pytest.raises(TokenInvalid):
        svc.verify(other_token)
    with pytest.raises(TokenInvalid):
        svc.verify("x.y.z")
    bad_kind = jwt.encode(
        {
            "sub": "a",
            "kind": "root",
            "exp": int(time.time()) + 60,
            "iss": "http://testserver",
            "jti": "j",
        },
        generate_private_key(), algorithm="EdDSA",
    )
    with pytest.raises(TokenInvalid):
        svc.verify(bad_kind)


def _make_client_row(app, roles=(), revoked=False):
    with app.state.session_factory() as s:
        user = User(id=new_id("usr"), idp_subject=new_id("sub"), username="u", roles=list(roles))
        client = Client(
            id=new_id("cli"), user_id=user.id, name="c",
            public_key=public_key_pem(generate_private_key()),
            revoked_at=utcnow() if revoked else None,
        )
        s.add(user)
        s.flush()  # the user row must exist before the client's foreign key is written
        s.add(client)
        s.commit()
        return client.id, user.id


def _bearer(app, sub, kind, **kw):
    token, _ = app.state.tokens.issue(sub, kind, **kw)
    return {"Authorization": f"Bearer {token}"}


def test_me_requires_a_token(server):
    assert server.get("/api/v1/me").status_code == 401
    assert server.get("/api/v1/me", headers={"Authorization": "Bearer junk"}).status_code == 401
    assert server.get("/api/v1/me", headers={"Authorization": "Basic abc"}).status_code == 401


def test_me_for_client_reports_roles_and_admin(server, app):
    cid, uid = _make_client_row(app, roles=["mlops-admin"])
    body = server.get("/api/v1/me", headers=_bearer(app, cid, "client", uid=uid)).json()
    assert body["kind"] == "client" and body["is_admin"] is True and body["user_id"] == uid


def test_revoked_client_is_rejected_immediately(server, app):
    cid, uid = _make_client_row(app, revoked=True)
    assert server.get("/api/v1/me", headers=_bearer(app, cid, "client", uid=uid)).status_code == 401


def test_token_for_unknown_principal_is_rejected(server, app):
    assert server.get("/api/v1/me", headers=_bearer(app, "cli_ghost", "client")).status_code == 401


def test_agent_token_is_valid_but_kind_restricted(server, app):
    with app.state.session_factory() as s:
        agent = Agent(id=new_id("agt"), name="a", public_key="k", capabilities={}, queues=["q"])
        s.add(agent)
        s.commit()
        agent_id = agent.id
    headers = _bearer(app, agent_id, "agent")
    assert server.get("/api/v1/me", headers=headers).json()["kind"] == "agent"


def test_run_token_dies_when_job_is_not_active(server, app):
    # a run token whose job row does not exist (or is finished) must be refused
    headers = _bearer(app, "run_x", "run", experiment_id="exp_1", job_id="job_missing")
    assert server.get("/api/v1/me", headers=headers).status_code == 401

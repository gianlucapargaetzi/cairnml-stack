import httpx
import pytest
import respx
from mlops_server.services.directory import DirectoryError, KeycloakDirectory

ISSUER = "http://mlops-idp:8080/realms/mlops"
ADMIN = "http://mlops-idp:8080/admin/realms/mlops"


def _token(router, expires_in=300):
    return router.post(f"{ISSUER}/protocol/openid-connect/token").respond(
        200, json={"access_token": "svc-token", "expires_in": expires_in})


@respx.mock
def test_enabled_user_with_effective_roles():
    token = _token(respx.mock)
    respx.get(f"{ADMIN}/users/u-1").respond(200, json={"id": "u-1", "enabled": True})
    respx.get(f"{ADMIN}/users/u-1/role-mappings/realm/composite").respond(
        200, json=[{"name": "mlops-admin"}, {"name": "default-roles-mlops"}])
    user = KeycloakDirectory(ISSUER, "mlops-server", "secret").get_user("u-1")
    assert user.enabled is True and user.roles == ("default-roles-mlops", "mlops-admin")
    sent = token.calls[0].request
    assert b"grant_type=client_credentials" in sent.content
    assert b"client_secret=secret" in sent.content


@respx.mock
def test_disabled_and_missing_users():
    _token(respx.mock)
    respx.get(f"{ADMIN}/users/u-2").respond(200, json={"enabled": False})
    respx.get(f"{ADMIN}/users/u-2/role-mappings/realm/composite").respond(200, json=[])
    respx.get(f"{ADMIN}/users/gone").respond(404)
    directory = KeycloakDirectory(ISSUER, "mlops-server", "secret")
    assert directory.get_user("u-2").enabled is False
    assert directory.get_user("gone") is None


@respx.mock
def test_the_subject_is_url_quoted_so_it_cannot_change_the_path():
    _token(respx.mock)
    seen = []

    def handler(request):
        seen.append(request.url.raw_path.decode())
        return httpx.Response(404)

    respx.get(url__regex=rf"{ADMIN}/users/.*").mock(side_effect=handler)
    assert KeycloakDirectory(ISSUER, "mlops-server", "secret").get_user("a/../b?x=1") is None
    assert seen == ["/admin/realms/mlops/users/a%2F..%2Fb%3Fx%3D1"]


@respx.mock
def test_token_is_cached_and_refreshed_after_a_401():
    token = _token(respx.mock)
    respx.get(f"{ADMIN}/users/u-3").mock(side_effect=[
        httpx.Response(401),
        httpx.Response(200, json={"enabled": True}),
        httpx.Response(200, json={"enabled": True}),
    ])
    respx.get(f"{ADMIN}/users/u-3/role-mappings/realm/composite").respond(200, json=[])
    directory = KeycloakDirectory(ISSUER, "mlops-server", "secret")
    assert directory.get_user("u-3").enabled
    assert token.call_count == 2  # first fetch plus the refresh after the 401
    directory.get_user("u-3")
    assert token.call_count == 2  # cached


@respx.mock
def test_failures_raise_directory_error():
    respx.post(f"{ISSUER}/protocol/openid-connect/token").respond(401)
    with pytest.raises(DirectoryError):
        KeycloakDirectory(ISSUER, "mlops-server", "bad").get_user("u")
    respx.mock.clear()
    _token(respx.mock)
    respx.get(f"{ADMIN}/users/u").respond(500)
    with pytest.raises(DirectoryError):
        KeycloakDirectory(ISSUER, "mlops-server", "secret").get_user("u")
    respx.mock.clear()
    _token(respx.mock)
    respx.get(f"{ADMIN}/users/u").mock(side_effect=httpx.ConnectError("down"))
    with pytest.raises(DirectoryError):
        KeycloakDirectory(ISSUER, "mlops-server", "secret").get_user("u")


def test_stub_directory_mirrors_the_database_by_default(server, enroll_client, stub_directory):
    carol = enroll_client("carol", roles=["mlops-admin"])
    assert stub_directory.get_user("sub-carol").roles == ("mlops-admin",)
    stub_directory.disable("sub-carol")
    assert stub_directory.get_user("sub-carol").enabled is False
    stub_directory.remove("sub-carol")
    assert stub_directory.get_user("sub-carol") is None
    assert carol.user_id


@respx.mock
@pytest.mark.parametrize("subject", [".", ".."])
def test_dot_segment_subjects_are_rejected_before_any_request(subject):
    token = _token(respx.mock)
    with pytest.raises(DirectoryError):
        KeycloakDirectory(ISSUER, "mlops-server", "secret").get_user(subject)
    assert token.call_count == 0
    assert len(respx.calls) == 0


@respx.mock
@pytest.mark.parametrize("token_reply, user_reply, roles_reply", [
    ({"json": {"expires_in": 300}}, None, None),                       # no access_token
    ({"json": ["not", "a", "dict"]}, None, None),                      # token body not an object
    ({"content": b"<html>"}, None, None),                              # token body not JSON
    ({"json": {"access_token": "t", "expires_in": "soon"}}, None, None),  # bad lifetime
    (None, {"json": ["enabled"]}, None),                               # user body not an object
    (None, {"json": {"id": "u-m"}}, None),                             # 200 without "enabled"
    (None, {"json": {"enabled": "false"}}, None),                      # "enabled" not a boolean
    (None, {"json": {"enabled": True}}, {"json": {"name": "mlops-admin"}}),  # roles not a list
    (None, {"json": {"enabled": True}}, {"json": [{"role": "mlops-admin"}]}),  # item without name
    (None, {"json": {"enabled": True}}, {"json": ["mlops-admin"]}),    # item not an object
])
def test_malformed_replies_raise_directory_error(token_reply, user_reply, roles_reply):
    respx.post(f"{ISSUER}/protocol/openid-connect/token").respond(
        200, **(token_reply or {"json": {"access_token": "svc-token", "expires_in": 300}}))
    respx.get(f"{ADMIN}/users/u-m").respond(200, **(user_reply or {"json": {"enabled": True}}))
    respx.get(f"{ADMIN}/users/u-m/role-mappings/realm/composite").respond(
        200, **(roles_reply or {"json": []}))
    with pytest.raises(DirectoryError):
        KeycloakDirectory(ISSUER, "mlops-server", "secret").get_user("u-m")


@respx.mock
def test_transport_errors_do_not_chain_the_httpx_request():
    _token(respx.mock)
    respx.get(f"{ADMIN}/users/u").mock(side_effect=httpx.ConnectError("down"))
    with pytest.raises(DirectoryError) as excinfo:
        KeycloakDirectory(ISSUER, "mlops-server", "secret").get_user("u")
    assert excinfo.value.__cause__ is None
    assert excinfo.value.__suppress_context__ is True

import pytest
from mlops_server.security.oidc import OidcError


def test_valid_token_yields_identity(idp):
    ident = idp.verifier().verify(idp.token(sub="s1", username="alice", roles=["mlops-admin"]))
    assert (ident.subject, ident.username, ident.roles) == ("s1", "alice", ("mlops-admin",))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"iss": "http://evil/realms/x"},
        {"azp": "another-client"},
        {"exp_in": -10},
    ],
)
def test_rejects_bad_claims(idp, kwargs):
    with pytest.raises(OidcError):
        idp.verifier().verify(idp.token(**kwargs))


def test_rejects_token_signed_by_other_key(idp):
    from cryptography.hazmat.primitives.asymmetric import rsa

    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(OidcError):
        idp.verifier().verify(idp.token(key=other))


def test_rejects_garbage(idp):
    with pytest.raises(OidcError):
        idp.verifier().verify("not-a-jwt")


def test_client_restriction_and_nonce(idp):
    verifier = idp.verifier()
    web_token = idp.token(azp="mlops-web")
    assert verifier.verify(web_token).username == "dev"
    with pytest.raises(OidcError):
        verifier.verify(web_token, clients=["mlops-cli"])
    id_token = idp.token(azp="mlops-web", extra={"nonce": "n-1"})
    verifier.verify_nonce(id_token, "n-1", clients=["mlops-web"])
    with pytest.raises(OidcError):
        verifier.verify_nonce(id_token, "other", clients=["mlops-web"])
    with pytest.raises(OidcError):
        no_nonce = idp.token(azp="mlops-web")
        verifier.verify_nonce(no_nonce, "n-1", clients=["mlops-web"])  # no nonce claim

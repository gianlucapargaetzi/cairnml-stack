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

import pytest
from mlops_common.assertion import (
    AssertionInvalid,
    make_assertion,
    unverified_issuer,
    verify_assertion,
)
from mlops_common.keys import generate_private_key

AUD = "http://mlops-server:8000"


def test_roundtrip_returns_claims():
    key = generate_private_key()
    token = make_assertion(key, "cli_abc", AUD, now=1000)
    claims = verify_assertion(token, key.public_key(), AUD, now=1001)
    assert claims["iss"] == "cli_abc"
    assert claims["exp"] == 1120
    assert unverified_issuer(token) == "cli_abc"


def test_audience_trailing_slash_is_ignored():
    key = generate_private_key()
    token = make_assertion(key, "cli_abc", AUD + "/", now=1000)
    verify_assertion(token, key.public_key(), AUD, now=1000)


def test_rejects_wrong_key_wrong_audience_and_garbage():
    key, other = generate_private_key(), generate_private_key()
    token = make_assertion(key, "cli_abc", AUD, now=1000)
    with pytest.raises(AssertionInvalid):
        verify_assertion(token, other.public_key(), AUD, now=1000)
    with pytest.raises(AssertionInvalid):
        verify_assertion(token, key.public_key(), "http://evil", now=1000)
    with pytest.raises(AssertionInvalid):
        verify_assertion("a.b.c", key.public_key(), AUD)
    with pytest.raises(AssertionInvalid):
        unverified_issuer("garbage")


def test_rejects_expired_and_future():
    key = generate_private_key()
    token = make_assertion(key, "cli_abc", AUD, ttl=60, now=1000)
    with pytest.raises(AssertionInvalid, match="expired"):
        verify_assertion(token, key.public_key(), AUD, now=1000 + 60 + 31)
    with pytest.raises(AssertionInvalid, match="future"):
        verify_assertion(token, key.public_key(), AUD, now=1000 - 31)
    verify_assertion(token, key.public_key(), AUD, now=1000 + 60 + 29)  # inside leeway


def test_rejects_long_lifetime():
    key = generate_private_key()
    token = make_assertion(key, "cli_abc", AUD, ttl=3600, now=1000)
    with pytest.raises(AssertionInvalid, match="lifetime"):
        verify_assertion(token, key.public_key(), AUD, now=1000)


def test_jti_is_unique():
    key = generate_private_key()
    a = verify_assertion(make_assertion(key, "cli_a", AUD, now=1), key.public_key(), AUD, now=1)
    b = verify_assertion(make_assertion(key, "cli_a", AUD, now=1), key.public_key(), AUD, now=1)
    assert a["jti"] != b["jti"]

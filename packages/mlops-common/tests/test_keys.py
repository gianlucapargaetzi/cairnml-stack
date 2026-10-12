import stat

import pytest
from mlops_common.keys import (
    generate_private_key,
    load_private_key,
    load_public_key,
    private_key_to_pem,
    public_key_pem,
    read_private_key,
    write_private_key,
)


def test_private_key_pem_roundtrip():
    key = generate_private_key()
    again = load_private_key(private_key_to_pem(key))
    assert public_key_pem(again) == public_key_pem(key)


def test_public_key_pem_roundtrip_and_rejects_garbage():
    key = generate_private_key()
    assert public_key_pem(load_public_key(public_key_pem(key))) == public_key_pem(key)
    with pytest.raises(ValueError):
        load_public_key("not a key")


def test_write_private_key_is_0600_and_refuses_overwrite(tmp_path):
    path = tmp_path / "sub" / "key.pem"
    write_private_key(path, generate_private_key())
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        write_private_key(path, generate_private_key())


def test_read_private_key_rejects_open_permissions(tmp_path):
    path = tmp_path / "key.pem"
    write_private_key(path, generate_private_key())
    path.chmod(0o644)
    with pytest.raises(PermissionError):
        read_private_key(path)
    path.chmod(0o600)
    assert read_private_key(path) is not None


def test_load_private_key_rejects_rsa():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    pem = rsa.generate_private_key(65537, 2048).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    with pytest.raises(ValueError):
        load_private_key(pem)

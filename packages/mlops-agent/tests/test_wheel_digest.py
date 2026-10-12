from mlops_agent.executors.python import venv_volume_name, wheels_digest


def test_digest_changes_with_the_files(tmp_path):
    assert wheels_digest(None) == "" and wheels_digest(tmp_path / "missing") == ""
    (tmp_path / "a.whl").write_bytes(b"1")
    first = wheels_digest(tmp_path)
    assert len(first) == 12 and first == wheels_digest(tmp_path)
    (tmp_path / "a.whl").write_bytes(b"12")  # rebuilt wheel with a different size
    assert wheels_digest(tmp_path) != first
    (tmp_path / "b.whl").write_bytes(b"1")
    assert wheels_digest(tmp_path) != wheels_digest(tmp_path / "missing")


def test_digest_detects_a_same_size_rebuild(tmp_path):
    (tmp_path / "a.whl").write_bytes(b"aaaa")
    first = wheels_digest(tmp_path)
    (tmp_path / "a.whl").write_bytes(b"bbbb")  # same name, same size, different content
    assert wheels_digest(tmp_path) != first


def test_volume_name_uses_the_digest():
    assert venv_volume_name("3.11", "", "spec", "aaa") != venv_volume_name(
        "3.11", "", "spec", "bbb"
    )
    assert venv_volume_name("3.11", "", "spec") == venv_volume_name("3.11", "", "spec", "")

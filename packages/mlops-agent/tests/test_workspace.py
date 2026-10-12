import httpx
import pytest
from mlops_agent.testing.helpers import git, make_origin
from mlops_agent.workspace import GitError, apply_patch, clone_at, download, safe_join


def test_clone_at_checks_out_the_exact_commit(tmp_path):
    web, sha = make_origin(tmp_path)
    dest = tmp_path / "ws"
    clone_at("owner/name", sha, dest, token="secret-token", web_url=web)
    assert (dest / "train.py").read_text() == "print(1)\n"
    assert git("rev-parse", "HEAD", cwd=dest) == sha
    assert "secret-token" not in (dest / ".git" / "config").read_text()


def test_clone_failure_does_not_leak_the_token(tmp_path):
    with pytest.raises(GitError) as err:
        clone_at(
            "owner/missing",
            "a" * 40,
            tmp_path / "ws",
            token="secret-token",
            web_url=f"file://{tmp_path}/nowhere",
        )
    assert "secret-token" not in str(err.value)


def test_apply_patch_adds_modifies_and_rejects_escapes(tmp_path):
    web, sha = make_origin(tmp_path)
    dest = tmp_path / "ws"
    clone_at("owner/name", sha, dest, token="t", web_url=web)
    patch = (
        b"diff --git a/train.py b/train.py\n--- a/train.py\n+++ b/train.py\n"
        b"@@ -1 +1 @@\n-print(1)\n+print(2)\n"
        b"diff --git a/new.txt b/new.txt\nnew file mode 100644\n--- /dev/null\n"
        b"+++ b/new.txt\n@@ -0,0 +1 @@\n+hello\n"
    )
    apply_patch(dest, patch)
    assert (dest / "train.py").read_text() == "print(2)\n" and (
        dest / "new.txt"
    ).read_text() == "hello\n"
    evil = (
        b"diff --git a/../evil b/../evil\nnew file mode 100644\n--- /dev/null\n"
        b"+++ b/../evil\n@@ -0,0 +1 @@\n+x\n"
    )
    with pytest.raises(GitError):
        apply_patch(dest, evil)
    assert not (tmp_path / "evil").exists()


def test_download_streams_to_file_and_enforces_limit(tmp_path):
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"x" * 1000))
    client = httpx.Client(transport=transport)
    download("http://nas/x", tmp_path / "a" / "b.bin", http=client)
    assert (tmp_path / "a" / "b.bin").stat().st_size == 1000
    with pytest.raises(ValueError, match="too large"):
        download("http://nas/x", tmp_path / "c.bin", http=client, max_bytes=10)
    assert not (tmp_path / "c.bin").exists()


@pytest.mark.parametrize("bad", ["../x", "a/../../x", "/etc/passwd"])
def test_safe_join_rejects_escapes(tmp_path, bad):
    with pytest.raises(ValueError):
        safe_join(tmp_path, bad)
    assert safe_join(tmp_path, "a/b.txt") == (tmp_path / "a" / "b.txt").resolve()


def test_scrub_removes_token_in_raw_and_base64_forms():
    import base64

    from mlops_agent.workspace import _auth_header, _scrub

    token = "ghs_secret123"
    b64 = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    plain_b64 = base64.b64encode(token.encode()).decode()
    text = f"raw {token} header {_auth_header(token)} bare {b64} plain {plain_b64}"
    scrubbed = _scrub(text, token)
    assert token not in scrubbed
    assert b64 not in scrubbed
    assert base64.b64encode(token.encode()).decode() not in scrubbed

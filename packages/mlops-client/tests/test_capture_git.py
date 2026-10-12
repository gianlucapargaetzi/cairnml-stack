import subprocess

import pytest
from mlops.capture.git import build_patch, capture_git, is_pushed, parse_repo_slug
from mlops.testing import git, make_repo


@pytest.mark.parametrize(
    "url,slug",
    [
        ("https://github.com/org/repo.git", "org/repo"),
        ("https://ghe.example.com/org/repo", "org/repo"),
        ("git@github.com:org/repo.git", "org/repo"),
        ("ssh://git@ghe.example.com/org/repo.git", "org/repo"),
        ("file:///srv/git/org/repo.git", "org/repo"),
        ("/srv/git/org/repo.git", "org/repo"),
        ("repo", None),
        ("", None),
    ],
)
def test_parse_repo_slug(url, slug):
    assert parse_repo_slug(url) == slug


def test_capture_clean_repo(tmp_path):
    work, _ = make_repo(tmp_path)
    state = capture_git(work)
    assert state.root == work.resolve() and state.branch == "main" and state.dirty is False
    assert state.commit == git("rev-parse", "HEAD", cwd=work) and state.repo == "owner/name"
    assert build_patch(work) == b""


def test_capture_from_a_subdirectory_and_outside_a_repo(tmp_path):
    work, _ = make_repo(tmp_path, {"src/a.py": "x = 1\n"})
    assert capture_git(work / "src").root == work.resolve()
    assert capture_git(tmp_path) is None


def test_repo_without_commits_is_not_captured(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    assert capture_git(tmp_path) is None


def test_detached_head_has_no_branch(tmp_path):
    work, _ = make_repo(tmp_path)
    git("checkout", "-q", "--detach", cwd=work)
    assert capture_git(work).branch is None


def test_patch_covers_modified_untracked_and_binary_files_without_touching_the_index(tmp_path):
    work, _ = make_repo(tmp_path, {"train.py": "print(1)\n", "keep.txt": "k\n"})
    (work / "train.py").write_text("print(2)\n")
    (work / "new.py").write_text("print('new')\n")
    (work / "blob.bin").write_bytes(bytes(range(256)))
    (work / ".gitignore").write_text("ignored.txt\n")
    (work / "ignored.txt").write_text("secret\n")
    git("add", "keep.txt", cwd=work)  # a staged state the patch builder must not disturb
    before = git("status", "--porcelain", cwd=work)
    assert capture_git(work).dirty is True
    patch = build_patch(work)
    assert git("status", "--porcelain", cwd=work) == before
    assert b"secret" not in patch and b"print(2)" in patch and b"new.py" in patch

    # round trip: applying the patch to a fresh checkout reproduces the working tree
    fresh = tmp_path / "fresh"
    git("clone", "-q", str(tmp_path / "origin" / "owner" / "name.git"), str(fresh), cwd=tmp_path)
    subprocess.run(["git", "apply", "--binary", "-"], cwd=fresh, input=patch, check=True)
    assert (fresh / "train.py").read_text() == "print(2)\n"
    assert (fresh / "new.py").read_text() == "print('new')\n"
    assert (fresh / "blob.bin").read_bytes() == bytes(range(256))
    assert not (fresh / "ignored.txt").exists()


def test_is_pushed(tmp_path):
    work, _ = make_repo(tmp_path)
    pushed = git("rev-parse", "HEAD", cwd=work)
    assert is_pushed(work, pushed) is True
    (work / "x.txt").write_text("x")
    git("add", "-A", cwd=work)
    git("commit", "-q", "-m", "local only", cwd=work)
    assert is_pushed(work, git("rev-parse", "HEAD", cwd=work)) is False


def test_remote_credentials_are_not_captured(tmp_path):
    work, _ = make_repo(tmp_path)
    git("remote", "set-url", "origin", "https://user:s3cret@github.com/owner/name.git", cwd=work)
    state = capture_git(work)
    assert state.remote_url == "https://github.com/owner/name.git"
    assert state.repo == "owner/name"
    assert "s3cret" not in repr(state)

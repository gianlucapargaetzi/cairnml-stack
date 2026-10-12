import argparse
import sys
import textwrap
from types import SimpleNamespace

import pytest
from mlops.capture import args as capargs
from mlops.capture.datasets import resolve_dataset
from mlops.capture.env import capture_environment, capture_requirements, redact_argv, redact_mapping
from mlops.capture.git import capture_git
from mlops.capture.script import find_script, relative_cwd
from mlops.testing import make_repo


def test_redact_mapping_and_argv():
    assert redact_mapping({"API_KEY": "abc", "lr": 0.1, "db_password": "x"}) == {
        "API_KEY": "***", "lr": 0.1, "db_password": "***"}
    argv = ["train.py", "--lr", "0.1", "--api-key=abc", "--token", "xyz", "--epochs", "3"]
    assert redact_argv(argv) == [
        "train.py", "--lr", "0.1", "--api-key=***", "--token", "***", "--epochs", "3"]
    assert redact_argv(["x.py", "ghp_" + "a" * 36, "AKIA" + "A" * 16]) == ["x.py", "***", "***"]


class _Dist:
    def __init__(self, name, version, direct_url=None):
        self.metadata = {"Name": name}
        self.version = version
        self._direct = direct_url

    def read_text(self, filename):
        return self._direct if filename == "direct_url.json" else None


def test_requirements_skip_local_editable_and_mlops(monkeypatch):
    dists = [
        _Dist("NumPy", "1.26.4"), _Dist("mlops-client", "0.1.0"), _Dist("mlops_common", "0.1.0"),
        _Dist("mylib", "0.0.1", '{"url": "file:///home/me/mylib", "dir_info": {"editable": true}}'),
        _Dist("fromgit", "1.0", '{"url": "https://github.com/o/r", "vcs_info": {"vcs": "git"}}'),
    ]
    monkeypatch.setattr("importlib.metadata.distributions", lambda: dists)
    assert capture_requirements() == ["fromgit==1.0", "numpy==1.26.4"]


def test_capture_environment_has_basics():
    env = capture_environment()
    assert env["python_version"].count(".") == 2
    assert env["cpu_count"] >= 1 and isinstance(env["gpus"], list)


@pytest.fixture
def clean_argparse():
    yield
    capargs.uninstall()


def test_argparse_capture_and_overrides(clean_argparse):
    captured = []
    overrides = {"lr": "0.5", "epochs": "7", "debug": "true", "unknown": 1}
    capargs.install(captured.append, overrides=overrides)
    parser = argparse.ArgumentParser()
    parser.add_argument("--lr", type=float, default=0.1)
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--name", default="x")
    ns = parser.parse_args(["--name", "run"])
    assert (ns.lr, ns.epochs, ns.debug, ns.name) == (0.5, 7, True, "run")
    assert captured == [{"lr": 0.5, "epochs": 7, "debug": True, "name": "run"}]


def test_subparsers_trigger_a_single_callback_and_uninstall_restores(clean_argparse):
    captured = []
    original = argparse.ArgumentParser.parse_known_args
    capargs.install(captured.append)
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")
    run = sub.add_parser("run")
    run.add_argument("--n", type=int, default=1)
    parser.parse_args(["run", "--n", "4"])
    assert len(captured) == 1 and captured[0]["n"] == 4 and captured[0]["cmd"] == "run"
    capargs.uninstall()
    assert argparse.ArgumentParser.parse_known_args is original


def test_non_json_values_are_stringified(clean_argparse):
    captured = []
    capargs.install(captured.append)
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", type=__import__("pathlib").Path, default="a/b")
    parser.parse_args([])
    assert captured[0]["path"] == "a/b"


def test_find_script_inside_and_outside_a_repo(tmp_path):
    work, _ = make_repo(tmp_path, {"src/train.py": "print(1)\n"})
    git = capture_git(work)
    inside = find_script(work / "src" / "train.py", git)
    assert inside.in_repo and inside.rel == "src/train.py"
    outside_file = tmp_path / "loose.py"
    outside_file.write_text("print(2)\n")
    outside = find_script(outside_file, git)
    assert not outside.in_repo and outside.rel is None
    assert find_script(tmp_path / "missing.py", git) is None


def test_find_script_ignores_interactive_sessions(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["-c"])
    monkeypatch.setitem(sys.modules, "__main__", SimpleNamespace())
    assert find_script() is None


def test_relative_cwd(tmp_path):
    work, _ = make_repo(tmp_path, {"src/train.py": "x\n"})
    git = capture_git(work)
    assert relative_cwd(git, work) == "." and relative_cwd(git, work / "src") == "src"
    assert relative_cwd(None) == "."


def test_resolve_dataset_from_dvc_file_and_dvc_lock(tmp_path):
    files = {
        "data/train.dvc": textwrap.dedent("""\
            outs:
            - md5: 1234abcd.dir
              size: 10
              nfiles: 2
              path: train
        """),
        "dvc.lock": textwrap.dedent("""\
            schema: '2.0'
            stages:
              prepare:
                cmd: python prep.py
                outs:
                - path: data/clean
                  md5: ffff0000.dir
                  size: 5
        """),
    }
    work, _ = make_repo(tmp_path, files)
    git = capture_git(work)
    train = resolve_dataset("data/train", git, base=work)
    assert (train.path, train.dvc_hash, train.repo, train.commit) == (
        "data/train", "1234abcd.dir", "owner/name", git.commit)
    assert resolve_dataset("data/clean", git, base=work).dvc_hash == "ffff0000.dir"


def test_resolve_dataset_errors(tmp_path):
    work, _ = make_repo(tmp_path)
    git = capture_git(work)
    with pytest.raises(ValueError, match="not tracked by DVC"):
        resolve_dataset("data/none", git, base=work)
    with pytest.raises(ValueError, match="git repository"):
        resolve_dataset("data/train", None)
    with pytest.raises(ValueError, match="outside"):
        resolve_dataset(tmp_path / "elsewhere", git, base=work)

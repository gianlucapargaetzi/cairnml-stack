import pytest
from mlops.cli import app as cli
from mlops.dataset_card import scaffold_card, write_card
from typer.testing import CliRunner


def test_scaffold_has_front_matter_from_the_dvc_metadata():
    text = scaffold_card(
        "data/train",
        {"dvc_hash": "abc.dir", "size_bytes": 100, "nfiles": 3},
        title="Train",
        license="MIT",
        type="images",
        description="Cars",
    )
    assert text.startswith("---\n") and "title: Train" in text and "license: MIT" in text
    assert (
        "size_bytes: 100" in text and "rows:" not in text and "# Train" in text and "Cars" in text
    )


def test_cli_card_init_creates_next_to_the_dvc_file_and_never_overwrites(
    tmp_path, monkeypatch, cfg_env
):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "train.dvc").write_text(
        "outs:\n- md5: abc.dir\n  size: 100\n  nfiles: 3\n  path: train\n"
    )
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    first = runner.invoke(
        cli, ["dataset", "card", "init", "data/train", "--title", "Train", "--license", "MIT"]
    )
    assert first.exit_code == 0 and "git add data/train.card.md" in first.output
    assert "size_bytes: 100" in (tmp_path / "data" / "train.card.md").read_text()
    again = runner.invoke(cli, ["dataset", "card", "init", "data/train"])
    assert again.exit_code == 1 and "already exists" in again.output
    missing = runner.invoke(cli, ["dataset", "card", "init", "data/none"])
    assert missing.exit_code == 1 and "not tracked by DVC" in missing.output


def test_cli_ls_and_show_read_the_server(sdk, stub_github):
    stub_github.add_repo("org/data")
    stub_github.add_commit("org/data", "1" * 40, message="add", date="2026-01-01T00:00:00Z")
    stub_github.add_branch("org/data", "main", "1" * 40)
    stub_github.set_file(
        "org/data", "data/train.dvc", "outs:\n- md5: abc.dir\n  size: 1\n  nfiles: 2\n"
    )
    stub_github.set_file(
        "org/data", "data/train.card.md", "---\ntitle: Train\ntype: tabular\n---\nHello body\n"
    )
    sdk.dev.http.post(
        "/api/v1/projects/repos", json={"project": "vision/seg", "repo": "org/data", "role": "data"}
    )
    runner = CliRunner()
    listed = runner.invoke(cli, ["dataset", "ls", "--project", "vision/seg"])
    assert listed.exit_code == 0 and "data/train" in listed.output and "card=yes" in listed.output
    shown = runner.invoke(cli, ["dataset", "show", "data/train", "--project", "vision/seg"])
    assert (
        shown.exit_code == 0 and "Train (tabular" in shown.output and "Hello body" in shown.output
    )
    missing = runner.invoke(cli, ["dataset", "show", "data/none", "--project", "vision/seg"])
    assert missing.exit_code == 1 and "no dataset" in missing.output


def test_card_text_is_stripped_of_terminal_escape_sequences(sdk, stub_github):
    stub_github.add_repo("org/data")
    stub_github.add_commit("org/data", "1" * 40, message="add", date="2026-01-01T00:00:00Z")
    stub_github.add_branch("org/data", "main", "1" * 40)
    stub_github.set_file(
        "org/data", "data/train.dvc", "outs:\n- md5: abc.dir\n  size: 1\n  nfiles: 2\n"
    )
    stub_github.set_file(
        "org/data",
        "data/train.card.md",
        '---\ntitle: "Bad\\e[31m title\\a"\n---\nHi\x1b]0;evil\x07 body\n',
    )
    sdk.dev.http.post(
        "/api/v1/projects/repos", json={"project": "vision/seg", "repo": "org/data", "role": "data"}
    )
    shown = CliRunner().invoke(cli, ["dataset", "show", "data/train", "--project", "vision/seg"])
    assert shown.exit_code == 0 and "Bad[31m title" in shown.output
    assert "\x1b" not in shown.output and "\x07" not in shown.output and "Hi" in shown.output


def test_scaffold_refuses_unsafe_paths_and_never_overwrites(tmp_path, monkeypatch):
    with pytest.raises(ValueError):
        scaffold_card("../outside", {})
    with pytest.raises(ValueError):
        scaffold_card("/etc/passwd", {})
    monkeypatch.chdir(tmp_path)
    (tmp_path / "keep.card.md").write_text("mine")
    with pytest.raises(FileExistsError):
        write_card("keep", {})
    assert (tmp_path / "keep.card.md").read_text() == "mine"

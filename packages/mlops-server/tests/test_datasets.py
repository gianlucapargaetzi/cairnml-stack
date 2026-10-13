import textwrap

import pytest
from mlops_server.services.datasets import front_matter, parse_card, parse_dvc

CARD = textwrap.dedent("""\
    ---
    title: Training images
    type: images
    license: CC-BY-4.0
    tags: [vision, cars]
    owners: [alice]
    size_bytes: 123456
    rows: 5000
    columns:
      - {name: path, type: string, description: image file}
      - {name: label, type: int}
    splits: {train: 4000, val: 1000}
    custom_key: kept
    ---
    # Training images

    Photos of **cars** with labels. See [source](https://example.com/data).
    """)

DVC = "outs:\n- md5: abc123.dir\n  size: 98765\n  nfiles: 5000\n  path: train\n"


def test_front_matter_variants():
    meta, body, error = front_matter(CARD)
    assert (
        error is None
        and meta["title"] == "Training images"
        and body.startswith("# Training images")
    )
    assert front_matter("just text") == ({}, "just text", None)
    assert front_matter("---\ntitle: x\n")[2] == "front matter is not closed"
    assert front_matter("---\n: : :\n---\nbody")[2].startswith("invalid YAML")
    assert front_matter("---\n- a\n---\nbody")[2] == "front matter must be a mapping"


def test_card_parsing_keeps_known_fields_and_extras():
    card = parse_card(CARD)
    assert (card.title, card.type, card.license) == ("Training images", "images", "CC-BY-4.0")
    assert card.columns[0].name == "path" and card.splits == {"train": 4000, "val": 1000}
    assert (
        card.extra == {"custom_key": "kept"}
        and card.warnings == []
        and card.body.startswith("# Training")
    )


def test_invalid_fields_are_dropped_with_a_warning():
    card = parse_card("---\ntitle: ok\ntype: hologram\nrows: many\n---\nbody")
    assert card.title == "ok" and card.type == "other" and card.rows is None
    assert len(card.warnings) == 2


def test_dvc_file_parsing():
    assert parse_dvc(DVC) == {"dvc_hash": "abc123.dir", "size_bytes": 98765, "nfiles": 5000}
    assert parse_dvc("garbage: [") == {"dvc_hash": None, "size_bytes": None, "nfiles": None}


@pytest.fixture
def lab(server, enroll_client, make_project, stub_github):
    dev = enroll_client("dev")
    make_project("vision/seg", members=["dev"])
    gh = stub_github
    gh.add_repo("org/data")
    gh.add_commit("org/data", "1" * 40, message="add train", date="2026-01-01T00:00:00Z")
    gh.add_commit("org/data", "2" * 40, ["1" * 40], "relabel", date="2026-01-02T00:00:00Z")
    gh.add_branch("org/data", "main", "2" * 40)
    gh.set_file("org/data", "data/train.dvc", DVC)
    gh.set_file("org/data", "data/train.card.md", CARD)
    gh.set_file(
        "org/data", "data/val.dvc", "outs:\n- md5: ff00.dir\n  size: 5\n  nfiles: 1\n  path: val\n"
    )
    gh.set_file("org/data", ".dvc/config", "[core]\n")
    gh.set_file("org/data", "README.md", "hi")
    gh.set_file_history("org/data", "data/train.dvc", ["2" * 40, "1" * 40])
    gh.set_file("org/data", f"data/train.dvc@{'1' * 40}", DVC.replace("abc123", "old999"))
    gh.set_file("org/data", f"data/train.dvc@{'2' * 40}", DVC)
    dev.http.post(
        "/api/v1/projects/repos", json={"project": "vision/seg", "repo": "org/data", "role": "data"}
    )
    return dict(dev=dev, gh=gh)


def test_dataset_list(lab):
    rows = lab["dev"].http.get("/api/v1/datasets", params={"project": "vision/seg"}).json()
    assert [r["path"] for r in rows] == ["data/train", "data/val"]
    train, val = rows
    assert (
        train["has_card"] is True and train["type"] == "images" and train["license"] == "CC-BY-4.0"
    )
    assert (
        train["dvc_hash"] == "abc123.dir"
        and train["size_bytes"] == 98765
        and train["nfiles"] == 5000
    )
    assert (
        val["has_card"] is False
        and val["type"] is None
        and train["repo"] == "org/data"
        and train["project"] == "vision/seg"
    )


def test_dataset_detail_with_versions_and_usage(lab):
    http = lab["dev"].http
    exp = http.post(
        "/api/v1/experiments",
        json={"project": "vision/seg", "name": "uses-data", "task": "training"},
    ).json()
    http.patch(
        f"/api/v1/experiments/{exp['id']}",
        json={"datasets": [{"path": "data/train", "dvc_hash": "abc123.dir", "repo": "org/data"}]},
    )
    body = http.get(
        "/api/v1/datasets/detail",
        params={"project": "vision/seg", "repo": "org/data", "path": "data/train"},
    ).json()
    assert body["card"]["title"] == "Training images" and body["card"]["body"].startswith(
        "# Training images"
    )
    assert body["dvc"]["dvc_hash"] == "abc123.dir"
    assert [(v["commit"], v["dvc_hash"]) for v in body["versions"]] == [
        ("2" * 40, "abc123.dir"),
        ("1" * 40, "old999.dir"),
    ]
    assert body["versions"][0]["message"] == "relabel"
    assert (
        body["used_by"]["count"] == 1 and body["used_by"]["experiments"][0]["name"] == "uses-data"
    )


def test_a_dataset_without_a_card_still_has_detail(lab):
    body = (
        lab["dev"]
        .http.get(
            "/api/v1/datasets/detail",
            params={"project": "vision/seg", "repo": "org/data", "path": "data/val"},
        )
        .json()
    )
    assert body["card"] is None and body["dvc"]["nfiles"] == 1


def test_access_rules_and_unknown_datasets(lab, enroll_client):
    http = lab["dev"].http
    params = {"project": "vision/seg", "repo": "org/data", "path": "data/nope"}
    assert http.get("/api/v1/datasets/detail", params=params).status_code == 404
    assert (
        http.get("/api/v1/datasets/detail", params={**params, "path": "../etc/passwd"}).status_code
        == 422
    )
    assert (
        http.get(
            "/api/v1/datasets/detail",
            params={**params, "path": "data/train", "repo": "org/unlinked"},
        ).status_code
        == 404
    )
    eve = enroll_client("eve")
    assert eve.http.get("/api/v1/datasets", params={"project": "vision/seg"}).status_code == 404
    assert eve.http.get("/api/v1/datasets").json() == []


def test_a_broken_repository_is_skipped_with_a_warning_header(lab, stub_github):
    stub_github.add_repo("org/other")
    lab["dev"].http.post(
        "/api/v1/projects/repos",
        json={"project": "vision/seg", "repo": "org/other", "role": "data"},
    )
    stub_github.inaccessible.add("org/other")
    response = lab["dev"].http.get("/api/v1/datasets", params={"project": "vision/seg"})
    assert (
        response.status_code == 200
        and len(response.json()) == 2
        and "org/other" in response.headers["x-dataset-warnings"]
    )


def test_unquoted_dates_and_numbers_are_kept_as_text():
    card = parse_card("---\ncreated: 2026-01-05\nversion: 1.2\n---\nbody")
    assert card.created == "2026-01-05" and card.version == "1.2" and card.warnings == []


def test_null_fields_and_malformed_dvc_outputs_are_not_errors():
    assert parse_card("---\ntags:\ntitle: ok\n---\nbody").warnings == []
    assert parse_dvc("outs: {md5: abc}") == {"dvc_hash": None, "size_bytes": None, "nfiles": None}
    assert parse_dvc("just a string") == {"dvc_hash": None, "size_bytes": None, "nfiles": None}


def test_unsafe_path_segments_and_refs_are_rejected_before_github(lab):
    http = lab["dev"].http
    lab["gh"].calls.clear()
    base = {"project": "vision/seg", "repo": "org/data", "path": "data/train"}
    for path in ("/etc/passwd", "data//train", "data/./train", "data/../x"):
        assert http.get("/api/v1/datasets/detail", params={**base, "path": path}).status_code == 422
    assert http.get("/api/v1/datasets/detail", params={**base, "ref": "a b"}).status_code == 422
    assert lab["gh"].calls == []


def test_non_string_yaml_keys_are_kept_as_text_and_listed(lab):
    card = "---\ntitle: Keys\ntrue: 1\n~: 2\n2026-01-01: 3\n---\nbody"
    parsed = parse_card(card)
    assert parsed.error is None and parsed.title == "Keys" and parsed.warnings == []
    assert parsed.extra == {"True": 1, "None": 2, "2026-01-01": 3}
    lab["gh"].set_file("org/data", "data/keys.dvc", DVC)
    lab["gh"].set_file("org/data", "data/keys.card.md", card)
    rows = lab["dev"].http.get("/api/v1/datasets", params={"project": "vision/seg"})
    assert rows.status_code == 200
    assert next(r for r in rows.json() if r["path"] == "data/keys")["title"] == "Keys"


BILLION_LAUGHS = (
    "---\n"
    + "a0: &a0 [x, x, x, x, x, x, x, x, x]\n"
    + "".join(f"a{i}: &a{i} [{', '.join([f'*a{i - 1}'] * 9)}]\n" for i in range(1, 7))
    + "---\nbody"
)


def test_alias_amplification_is_refused(lab):
    card = parse_card(BILLION_LAUGHS)
    assert card.error is not None and card.extra == {}
    lab["gh"].set_file("org/data", "data/bomb.dvc", DVC)
    lab["gh"].set_file("org/data", "data/bomb.card.md", BILLION_LAUGHS)
    rows = lab["dev"].http.get("/api/v1/datasets", params={"project": "vision/seg"})
    assert rows.status_code == 200
    assert next(r for r in rows.json() if r["path"] == "data/bomb")["has_card"] is True


def test_deep_nesting_and_large_front_matter_are_refused():
    deep = "---\nx: " + "[" * 25 + "]" * 25 + "\n---\nbody"
    assert parse_card(deep).error == "front matter is nested too deeply"
    big = "---\nx: " + "a" * (65 * 1024) + "\n---\nbody"
    assert parse_card(big).error.startswith("front matter is larger than 64 KB")
    assert parse_card(big).extra == {}


def test_a_truncated_tree_is_reported_in_the_warning_header(lab, stub_github):
    stub_github.truncated.add("org/data")
    response = lab["dev"].http.get("/api/v1/datasets", params={"project": "vision/seg"})
    assert response.status_code == 200 and len(response.json()) == 2
    assert "org/data (listing truncated by GitHub)" in response.headers["x-dataset-warnings"]


def test_a_missing_dataset_is_not_cached(lab, app):
    http = lab["dev"].http
    base = {"project": "vision/seg", "repo": "org/data"}
    before = len(app.state.dataset_cache)
    for _ in range(2):
        assert (
            http.get("/api/v1/datasets/detail", params={**base, "path": "data/nope"}).status_code
            == 404
        )
    assert len(app.state.dataset_cache) == before
    assert (
        http.get("/api/v1/datasets/detail", params={**base, "path": "data/train"}).status_code
        == 200
    )
    assert len(app.state.dataset_cache) == before + 1

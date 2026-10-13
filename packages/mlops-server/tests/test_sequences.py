"""Sequences: presigned uploads, registration of image, audio, text, figure and distribution
items, and the explorer search over them, with project scoping and sampling."""

from __future__ import annotations

import pytest


def _run(client, project: str, name: str) -> str:
    return client.http.post("/api/v1/runs", json={"project": project, "name": name}).json()["id"]


def _image(run: str, name: str, step: int, idx: int = 0, context=None, fmt="png") -> dict:
    return {"kind": "image", "name": name, "step": step, "idx": idx, "ts": 1.0,
            "context": context or {}, "format": fmt, "width": 8, "height": 4,
            "blob_key": None, "caption": f"{name} {step}"}


@pytest.fixture
def lab(server, enroll_client, make_project):
    dev = enroll_client("dev")
    eve = enroll_client("eve")
    make_project("vision/seg", members=["dev"])
    make_project("secret/lab", members=["eve"])
    run = _run(dev, "vision/seg", "fast")
    other = _run(eve, "secret/lab", "hidden")
    return {"dev": dev, "eve": eve, "run": run, "other": other}


def _presign(client, run, kind, name, step, idx=0, context=None, fmt="png"):
    body = {"kind": kind, "name": name, "step": step, "idx": idx, "format": fmt,
            "context": context or {}}
    response = client.http.post(f"/api/v1/runs/{run}/sequences/presign", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def _register(client, run, items):
    return client.http.post(f"/api/v1/runs/{run}/sequences", json={"items": items})


def _upload(client, run, name, step, idx=0, context=None, fmt="png"):
    """Presign and register one image item, as the SDK does."""
    presigned = _presign(client, run, "image", name, step, idx, context, fmt)
    item = _image(run, name, step, idx, context, fmt)
    item["blob_key"] = presigned["key"]
    response = _register(client, run, [item])
    assert response.status_code == 200, response.text
    return presigned


def test_presign_key_follows_the_layout_and_adds_a_context_segment(lab):
    plain = _presign(lab["dev"], lab["run"], "image", "pred", step=3, idx=1)
    assert plain["key"] == f"vision/seg/{lab['run']}/image/pred/3_1.png"
    assert plain["upload_url"].startswith("https://nas.test/")
    tagged = _presign(lab["dev"], lab["run"], "image", "pred", step=3,
                      context={"subset": "val"})
    assert "/image/pred/ctx-" in tagged["key"]
    assert tagged["key"] != plain["key"]


@pytest.mark.parametrize("name", ["../escape", "/abs", "a//b"])
def test_presign_refuses_unsafe_names(lab, name):
    response = lab["dev"].http.post(
        f"/api/v1/runs/{lab['run']}/sequences/presign",
        json={"kind": "image", "name": name, "step": 0, "format": "png"},
    )
    assert response.status_code == 422


def test_register_refuses_a_key_that_is_not_the_items_own(lab):
    item = _image(lab["run"], "pred", 0)
    item["blob_key"] = f"vision/seg/{lab['run']}/image/other/0_0.png"
    response = _register(lab["dev"], lab["run"], [item])
    assert response.status_code == 422


def test_register_binary_item_needs_a_blob_key_and_format(lab):
    item = _image(lab["run"], "pred", 0)
    item["format"] = None
    assert _register(lab["dev"], lab["run"], [item]).status_code == 422
    item = _image(lab["run"], "pred", 0)
    item["blob_key"] = None
    assert _register(lab["dev"], lab["run"], [item]).status_code == 422


def test_register_text_and_distribution_inline_and_retry_is_idempotent(lab):
    run = lab["run"]
    items = [
        {"kind": "text", "name": "log", "step": 0, "ts": 1.0, "text": "epoch 0"},
        {"kind": "distribution", "name": "weights", "step": 0, "ts": 1.0,
         "data": {"bin_counts": [1, 4, 2], "bin_range": [0.0, 1.0]}},
    ]
    assert _register(lab["dev"], run, items).json() == {"accepted": 2}
    # A retry of the same batch adds nothing.
    assert _register(lab["dev"], run, items).json() == {"accepted": 0}


def test_register_refuses_a_value_of_the_wrong_shape(lab):
    run = lab["run"]
    missing_text = {"kind": "text", "name": "log", "step": 0, "ts": 1.0}
    assert _register(lab["dev"], run, [missing_text]).status_code == 422
    bad_distribution = {"kind": "distribution", "name": "w", "step": 0, "ts": 1.0,
                        "data": {"bin_counts": "many"}}
    assert _register(lab["dev"], run, [bad_distribution]).status_code == 422
    huge = {"kind": "figure", "name": "f", "step": 0, "ts": 1.0,
            "data": {"x": "y" * 300_000}}
    assert _register(lab["dev"], run, [huge]).status_code == 422


def test_search_images_returns_items_with_presigned_urls(lab):
    _upload(lab["dev"], lab["run"], "pred", step=0)
    _upload(lab["dev"], lab["run"], "pred", step=1)
    response = lab["dev"].http.get("/api/v1/explorer/runs/search/images",
                                   params={"q": "images.name == 'pred'"})
    assert response.status_code == 200, response.text
    run = response.json()["runs"][lab["run"]]
    (sequence,) = run["sequences"]
    assert sequence["name"] == "pred" and sequence["context"] == {}
    steps = [item["step"] for item in sequence["items"]]
    assert steps == [0, 1]
    first = sequence["items"][0]
    assert first["blob_uri"].startswith("https://nas.test/") and first["format"] == "png"
    assert first["width"] == 8 and first["caption"] == "pred 0"


def test_search_text_returns_the_value_inline(lab):
    lab["dev"].http.post(f"/api/v1/runs/{lab['run']}/sequences", json={"items": [
        {"kind": "text", "name": "log", "step": 2, "ts": 1.0, "text": "hello"},
    ]})
    body = lab["dev"].http.get("/api/v1/explorer/runs/search/texts").json()
    (sequence,) = body["runs"][lab["run"]]["sequences"]
    assert sequence["items"][0]["text"] == "hello" and "blob_uri" not in sequence["items"][0]


def test_sequence_clauses_belong_to_their_own_search(lab):
    _upload(lab["dev"], lab["run"], "pred", step=0)
    wrong_kind = lab["dev"].http.get("/api/v1/explorer/runs/search/audios",
                                     params={"q": "images.name == 'pred'"})
    assert wrong_kind.status_code == 400
    in_run_search = lab["dev"].http.get("/api/v1/explorer/runs/search",
                                        params={"q": "images.name == 'pred'"})
    assert in_run_search.status_code == 400


def test_record_density_samples_steps_and_index_density_samples_items(lab):
    for step in range(10):
        for idx in range(3):
            _upload(lab["dev"], lab["run"], "pred", step=step, idx=idx)
    body = lab["dev"].http.get("/api/v1/explorer/runs/search/images", params={
        "q": "images.name == 'pred'", "record_density": 3, "index_density": 2,
    }).json()
    items = body["runs"][lab["run"]]["sequences"][0]["items"]
    steps = sorted({item["step"] for item in items})
    assert len(steps) == 3 and steps[0] == 0 and steps[-1] == 9
    per_step = {step: [i["idx"] for i in items if i["step"] == step] for step in steps}
    assert all(len(indices) == 2 for indices in per_step.values())


def test_record_range_limits_the_steps(lab):
    for step in range(6):
        _upload(lab["dev"], lab["run"], "pred", step=step)
    body = lab["dev"].http.get("/api/v1/explorer/runs/search/images", params={
        "q": "images.name == 'pred'", "record_range": "2:4",
    }).json()
    items = body["runs"][lab["run"]]["sequences"][0]["items"]
    assert sorted({item["step"] for item in items}) == [2, 3, 4]


def test_other_projects_sequences_are_not_searched(lab):
    _upload(lab["eve"], lab["other"], "secret", step=0)
    dev_view = lab["dev"].http.get("/api/v1/explorer/runs/search/images").json()
    assert lab["other"] not in dev_view["runs"]


def test_project_params_lists_sequence_names_and_context_keys(lab):
    _upload(lab["dev"], lab["run"], "pred", step=0, context={"subset": "val"})
    project_id = next(p["id"] for p in lab["dev"].http.get("/api/v1/projects").json()
                      if p["slug"] == "vision/seg")
    listing = lab["dev"].http.get(f"/api/v1/explorer/projects/{project_id}/params").json()
    assert listing["images"] == {"pred": ["subset"]}
    assert listing["texts"] == {}


def test_search_reports_the_step_and_index_ranges_the_sliders_read(lab):
    """The totals cover every matching item, as [low, high + 1]; the used ranges cover the
    items in this response."""
    for step in range(5):
        for idx in range(3):
            _upload(lab["dev"], lab["run"], "pred", step=step, idx=idx)
    body = lab["dev"].http.get("/api/v1/explorer/runs/search/images", params={
        "q": "images.name == 'pred'", "record_density": 2, "index_density": 1,
    }).json()
    ranges = body["runs"][lab["run"]]["ranges"]
    assert ranges["record_range_total"] == [0, 5]
    assert ranges["index_range_total"] == [0, 3]
    items = body["runs"][lab["run"]]["sequences"][0]["items"]
    used_steps = sorted({item["step"] for item in items})
    assert ranges["record_range_used"] == [used_steps[0], used_steps[-1] + 1]
    assert ranges["index_range_used"] == [0, 1]

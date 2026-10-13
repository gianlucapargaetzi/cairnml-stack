"""log_image, log_audio, log_text, log_figure and log_distribution: what the SDK sends, what the
explorer returns, what is refused in user code, and what survives an offline run."""

from __future__ import annotations

import struct

import httpx
import mlops
import pytest
from mlops import runtime
from mlops.api import ApiClient
from mlops.sync import sync_all


def _png(width: int = 8, height: int = 4) -> bytes:
    """A PNG header with the given size. The SDK reads the size and the magic bytes only."""
    return (b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + struct.pack(">II", width, height)
            + b"\x08\x06\x00\x00\x00" + b"\x00" * 8)


def _search(client, kind: str, query: str | None = None) -> list[dict]:
    params = {"project": "vision/seg"}
    if query:
        params["q"] = query
    response = client.http.get(f"/api/v1/explorer/runs/search/{kind}", params=params)
    assert response.status_code == 200, response.text
    return list(response.json()["runs"].values())


def _sequence(client, kind: str, run_name: str, name: str, context=None) -> dict:
    (run,) = [r for r in _search(client, kind) if r["props"]["name"] == run_name]
    (sequence,) = [s for s in run["sequences"] if s["name"] == name
                   and s["context"] == (context or {})]
    return sequence


def test_log_image_uploads_the_bytes_then_the_explorer_returns_the_item(sdk, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run = mlops.init("vision/seg", "pictures", capture_git=False)
    picture = _png()
    run.log_image("pred", picture, step=0, caption="first")
    assert any(data == picture for _, data in sdk.uploads)
    item = _sequence(sdk.dev, "images", "pictures", "pred")["items"][0]
    assert (item["step"], item["width"], item["height"]) == (0, 8, 4)
    assert item["format"] == "png" and item["caption"] == "first"
    assert item["blob_uri"].startswith("https://nas.test/")


def test_log_image_accepts_a_file_and_numbers_steps_per_name(sdk, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run = mlops.init("vision/seg", "numbered", capture_git=False)
    path = tmp_path / "frame.png"
    path.write_bytes(_png(2, 2))
    run.log_image("frames", path)
    run.log_image("frames", _png(2, 2))
    steps = [i["step"] for i in _sequence(sdk.dev, "images", "numbered", "frames")["items"]]
    assert steps == [0, 1]


def test_text_figure_and_distribution_are_stored_inline(sdk, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run = mlops.init("vision/seg", "inline", capture_git=False)
    run.log_text("log", "epoch 0 done", step=0)
    run.log_figure("curve", {"data": [{"type": "scatter", "x": [1, 2], "y": [3, 4]}]}, step=0)
    run.log_distribution("weights", [0.1, 0.2, 0.2, 0.9], step=0)
    text = _sequence(sdk.dev, "texts", "inline", "log")["items"][0]
    assert text["text"] == "epoch 0 done" and "blob_uri" not in text
    figure = _sequence(sdk.dev, "figures", "inline", "curve")["items"][0]
    assert figure["data"]["data"][0]["type"] == "scatter"
    distribution = _sequence(sdk.dev, "distributions", "inline", "weights")["items"][0]
    counts = distribution["data"]["bin_counts"]
    assert sum(counts) == 4 and len(counts) == 64
    assert distribution["data"]["bin_range"] == [0.1, 0.9]


def test_a_context_keeps_the_same_name_apart(sdk, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run = mlops.init("vision/seg", "contexts", capture_git=False)
    run.log_text("log", "train")
    run.log_text("log", "val", context={"subset": "val"})
    assert _sequence(sdk.dev, "texts", "contexts", "log")["items"][0]["text"] == "train"
    val = _sequence(sdk.dev, "texts", "contexts", "log", {"subset": "val"})
    assert val["items"][0]["text"] == "val"


@pytest.mark.parametrize(
    "call",
    [
        lambda run: run.log_image("pictures", b"not an image"),
        lambda run: run.log_image("../escape", _png()),
        lambda run: run.log_image("bad name", _png()),
        lambda run: run.log_image("pictures", _png(), context={"k": "x" * 200}),
        lambda run: run.log_audio("clip", b"junk bytes"),
        lambda run: run.log_text("log", 5),
        lambda run: run.log_figure("curve", object()),
        lambda run: run.log_distribution("weights", []),
        lambda run: run.log_distribution("weights", [1.0, float("nan")]),
    ],
)
def test_values_that_cannot_be_stored_are_refused_before_sending(sdk, tmp_path, monkeypatch, call):
    monkeypatch.chdir(tmp_path)
    run = mlops.init("vision/seg", "refused", capture_git=False)
    with pytest.raises(ValueError):
        call(run)
    assert not any("/image/" in url or "/audio/" in url for url, _ in sdk.uploads)
    assert not any(r["props"]["name"] == "refused" for r in _search(sdk.dev, "images"))
    assert not any(r["props"]["name"] == "refused" for r in _search(sdk.dev, "texts"))


def _offline_run(tmp_path, monkeypatch, name: str):
    """A run started while the server is unreachable, as in test_repo_data_sync."""
    def down(request):
        raise httpx.ConnectError("refused")

    broken = ApiClient(
        httpx.Client(base_url="http://mlops-server:8000", transport=httpx.MockTransport(down))
    )
    previous = runtime._override
    runtime.set_api_override(lambda token, url: broken)
    monkeypatch.chdir(tmp_path)
    try:
        run = mlops.init("vision/seg", name, capture_git=False)
        run.log_image("pred", _png(), step=0)
        run.log_text("log", "saved while offline", step=0)
        run.close()
    finally:
        runtime.set_api_override(previous)
    return run


def test_offline_sequences_are_spooled_and_synced_once(sdk, tmp_path, monkeypatch):
    _offline_run(tmp_path, monkeypatch, "seq-offline")
    failed: list[str] = []
    assert sync_all(sdk.api, put=lambda url, source, http=None: None, failed=failed) != []
    assert failed == []
    run_name = "seq-offline"
    assert len(_sequence(sdk.dev, "images", run_name, "pred")["items"]) == 1
    assert _sequence(sdk.dev, "texts", run_name, "log")["items"][0]["text"] == "saved while offline"
    # A second sync finds nothing left to send.
    assert sync_all(sdk.api, put=lambda url, source, http=None: None) == []


def test_a_failed_blob_upload_keeps_the_spool_and_the_retry_registers_once(
    sdk, tmp_path, monkeypatch
):
    _offline_run(tmp_path, monkeypatch, "seq-retry")

    def storage_down(url, source, http=None):
        # Only the image upload fails; the run's own artifacts sync first and succeed.
        if "/image/" in url:
            raise httpx.ConnectError("storage down")

    failed: list[str] = []
    assert sync_all(sdk.api, put=storage_down, failed=failed) == []
    assert failed and "image pred" in failed[0]
    synced = sync_all(sdk.api, put=lambda url, source, http=None: None)
    assert len(synced) == 1
    assert len(_sequence(sdk.dev, "images", "seq-retry", "pred")["items"]) == 1

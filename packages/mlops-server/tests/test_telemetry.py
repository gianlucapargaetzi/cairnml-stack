import time


def _exp(dev, make_project):
    make_project("vision/seg", members=["dev"])
    created = dev.http.post(
        "/api/v1/experiments", json={"project": "vision/seg", "name": "n"}
    )
    return created.json()["id"]


def test_metrics_roundtrip_and_ordering(server, enroll_client, make_project):
    dev = enroll_client("dev")
    exp = _exp(dev, make_project)
    pts = [
        {"name": "loss", "value": v, "step": s, "ts": time.time()}
        for s, v in [(2, 0.5), (1, 0.9)]
    ]
    posted = dev.http.post(f"/api/v1/experiments/{exp}/metrics", json={"points": pts})
    assert posted.json() == {"accepted": 2}
    series = dev.http.get(f"/api/v1/experiments/{exp}/metrics", params={"name": "loss"}).json()
    assert [p["step"] for p in series["loss"]] == [1, 2]


def test_log_batches_are_idempotent(server, enroll_client, make_project):
    dev = enroll_client("dev")
    exp = _exp(dev, make_project)
    batch = {"stream": "stdout", "seq": 0, "lines": [{"ts": 1.0, "text": "hello"}]}
    url = f"/api/v1/experiments/{exp}/logs"
    assert dev.http.post(url, json=batch).json() == {"accepted": 1}
    assert dev.http.post(url, json=batch).json() == {"duplicate": True}
    dev.http.post(url, json={**batch, "seq": 1, "lines": [{"ts": 2.0, "text": "world"}]})
    chunks = dev.http.get(url, params={"stream": "stdout"}).json()
    assert [c["seq"] for c in chunks] == [0, 1]
    assert [c["seq"] for c in dev.http.get(url, params={"after_seq": 0}).json()] == [1]


def test_oversized_and_overlong_inputs(server, enroll_client, make_project):
    dev = enroll_client("dev")
    exp = _exp(dev, make_project)
    url = f"/api/v1/experiments/{exp}/logs"
    huge = {"stream": "stdout", "seq": 0, "lines": [{"ts": 1.0, "text": "x" * 16_000}] * 130}
    assert dev.http.post(url, json=huge).status_code == 413
    long_line = {"stream": "stderr", "seq": 0, "lines": [{"ts": 1.0, "text": "y" * 20_000}]}
    dev.http.post(url, json=long_line)
    stored = dev.http.get(url, params={"stream": "stderr"}).json()[0]["lines"][0]["text"]
    assert len(stored) < 17_000 and stored.endswith("[truncated]")
    assert dev.http.post(url, json={"stream": "stdout", "seq": 1, "lines": []}).status_code == 422


def test_other_users_cannot_write_telemetry(server, enroll_client, make_project):
    dev = enroll_client("dev")
    exp = _exp(dev, make_project)
    enroll_client("eve")
    make_project("vision/seg", members=["eve"])
    eve = enroll_client("eve")
    body = {"points": [{"name": "x", "value": 1.0, "ts": 1.0}]}
    assert eve.http.post(f"/api/v1/experiments/{exp}/metrics", json=body).status_code == 404

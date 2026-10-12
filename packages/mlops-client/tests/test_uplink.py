import threading

import httpx
import pytest
from mlops.spool import Spool
from mlops.transfer import put_file
from mlops.uplink import Uplink, replay


class FakeApi:
    def __init__(self, fail=0, status=None):
        self.metrics, self.logs, self.fail, self.status = [], [], fail, status

    def _maybe_fail(self):
        if self.fail:
            self.fail -= 1
            if self.status:
                raise httpx.HTTPStatusError(
                    "x",
                    request=httpx.Request("POST", "http://x"),
                    response=httpx.Response(self.status),
                )
            raise httpx.ConnectError("down")

    def post_metrics(self, exp, points):
        self._maybe_fail()
        self.metrics.append((exp, points))

    def post_logs(self, exp, stream, seq, lines):
        self._maybe_fail()
        self.logs.append((exp, stream, seq, [line["text"] for line in lines]))

    def patch_experiment(self, exp, **fields):
        self._maybe_fail()


def _uplink(tmp_path, api, **kw):
    return Uplink(
        api, "exp_1", Spool(tmp_path / "spool" / "exp_1", {"experiment_id": "exp_1"}), **kw
    )


def test_metrics_and_logs_are_batched_with_sequences(tmp_path):
    api = FakeApi()
    up = _uplink(tmp_path, api, max_batch=2)
    for i in range(3):
        up.metric("loss", 1.0 / (i + 1), i)
    up.log("stdout", "a")
    up.log("stdout", "b")
    up.flush()
    up.log("stdout", "c")
    up.flush()
    assert [len(p) for _, p in api.metrics] == [2, 1]
    assert [(s, seq, t) for _, s, seq, t in api.logs] == [
        ("stdout", 0, ["a", "b"]),
        ("stdout", 1, ["c"]),
    ]
    assert not up.degraded and not up._spool.exists()


def test_transient_failure_spools_and_later_replays_in_order(tmp_path):
    api = FakeApi(fail=1)
    up = _uplink(tmp_path, api)
    up.metric("loss", 1.0, 0)
    up.flush()  # fails, spooled
    assert up.degraded and up._spool.events()[0]["kind"] == "metrics"
    up.metric("loss", 0.5, 1)
    up.close()  # sends the new point, then replays the spooled batch
    assert [p[0]["step"] for _, p in api.metrics] == [1, 0]
    assert not up._spool.exists()


def test_replay_stops_at_first_failure_and_keeps_the_rest(tmp_path):
    spool = Spool(tmp_path / "s", {"experiment_id": "exp_1"})
    spool.append("metrics", {"points": [{"name": "a", "value": 1, "step": 0, "ts": 1}]})
    spool.append("logs", {"stream": "stdout", "seq": 0, "lines": [{"ts": 1, "text": "x"}]})
    spool.append("metrics", {"points": [{"name": "b", "value": 2, "step": 1, "ts": 2}]})

    class Flaky(FakeApi):
        def post_logs(self, *a, **k):
            raise httpx.ConnectError("down")

    api = Flaky()
    assert replay(spool, api, "exp_1") == 1
    assert [e["kind"] for e in spool.events()] == [
        "logs",
        "metrics",
    ]  # first one is gone, no duplicates later
    assert replay(spool, FakeApi(), "exp_1") == 2 and not spool.exists()


def test_client_errors_drop_the_batch_without_spooling(tmp_path):
    api = FakeApi(fail=1, status=422)
    up = _uplink(tmp_path, api)
    up.metric("x", 1.0, 0)
    up.flush()
    assert not up._spool.exists() and not up.degraded


def test_server_errors_are_spooled(tmp_path):
    api = FakeApi(fail=1, status=503)
    up = _uplink(tmp_path, api)
    up.metric("x", 1.0, 0)
    up.flush()
    assert up._spool.exists() and up.degraded


def test_without_an_api_everything_is_spooled(tmp_path):
    up = Uplink(None, None, Spool(tmp_path / "off", {"local_id": "offline_1"}))
    up.metric("x", 1.0, 0)
    up.log("stderr", "oops")
    up.close()
    kinds = [e["kind"] for e in up._spool.events()]
    assert kinds == ["metrics", "logs"] and up._spool.meta()["local_id"] == "offline_1"


def test_background_thread_flushes(tmp_path):
    api = FakeApi()
    up = _uplink(tmp_path, api, flush_s=0.05)
    up.start()
    up.metric("x", 1.0, 0)
    for _ in range(100):
        if api.metrics:
            break
        threading_wait()
    up.close()
    assert api.metrics


def threading_wait():
    threading.Event().wait(0.02)


def test_spool_file_path_rejects_traversal(tmp_path):
    spool = Spool(tmp_path / "s")
    assert spool.file_path("a/b.bin").parent.is_dir()
    with pytest.raises(ValueError):
        spool.file_path("../x")


def test_put_file_sends_content_length_and_streams(tmp_path):
    seen = {}

    def handler(request):
        seen["length"] = request.headers["content-length"]
        seen["body"] = request.read()
        return httpx.Response(200)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    path = tmp_path / "f.bin"
    path.write_bytes(b"x" * 3000)
    put_file("http://nas/x", path, http=client)
    assert seen["length"] == "3000" and seen["body"] == b"x" * 3000
    put_file("http://nas/x", b"abc", http=client)
    assert seen["length"] == "3"
    bad = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(403)))
    with pytest.raises(httpx.HTTPStatusError):
        put_file("http://nas/x", b"abc", http=bad)

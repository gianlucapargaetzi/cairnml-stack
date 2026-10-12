from mlops_agent.logship import LogShipper


class Recorder:
    def __init__(self, fail_times=0):
        self.calls, self.fail_times = [], fail_times

    def __call__(self, stream, seq, lines):
        if self.fail_times:
            self.fail_times -= 1
            raise RuntimeError("down")
        self.calls.append((stream, seq, [entry["text"] for entry in lines]))


def _shipper(rec, **kw):
    return LogShipper(rec, "stdout", sleep=lambda s: None, **kw)


def test_batches_by_max_lines_with_increasing_seq():
    rec = Recorder()
    ship = _shipper(rec, max_lines=2)
    for i in range(5):
        ship.write(f"l{i}")
    ship.flush()
    assert rec.calls == [
        ("stdout", 0, ["l0", "l1"]),
        ("stdout", 1, ["l2", "l3"]),
        ("stdout", 2, ["l4"]),
    ]


def test_failed_post_is_retried_with_the_same_seq():
    rec = Recorder(fail_times=2)
    ship = _shipper(rec)
    ship.write("a")
    ship.flush()
    assert rec.calls == [("stdout", 0, ["a"])]


def test_persistent_failure_keeps_lines_for_next_flush():
    rec = Recorder(fail_times=4)  # 1 + 3 retries all fail
    ship = _shipper(rec)
    ship.write("a")
    ship.flush()
    assert rec.calls == []
    ship.write("b")
    ship.flush()
    assert rec.calls == [("stdout", 0, ["a", "b"])]


def test_scrub_is_applied_before_buffering():
    rec = Recorder()
    ship = _shipper(rec, scrub=lambda s: s.replace("TOKEN", "***"))
    ship.write("auth TOKEN ok")
    ship.flush()
    assert rec.calls[0][2] == ["auth *** ok"]


def test_buffer_overflow_drops_oldest_and_says_so():
    rec = Recorder()
    ship = _shipper(rec, max_buffer=3, max_lines=100)
    for i in range(6):
        ship.write(f"l{i}")
    ship.flush()
    texts = rec.calls[0][2]
    assert texts[-3:] == ["l3", "l4", "l5"] and "dropped" in texts[0]


def test_close_flushes_remaining_lines():
    rec = Recorder()
    ship = _shipper(rec)
    ship.start()
    ship.write("last")
    ship.close()
    assert rec.calls[-1][2] == ["last"]


def test_overflow_during_post_keeps_unsent_lines():
    ship = None
    sent = []

    def post(stream, seq, lines):
        if not sent:
            # Lines written while the first batch is in flight overflow the buffer.
            for i in range(3, 6):
                ship.write(f"l{i}")
        sent.append([entry["text"] for entry in lines])

    ship = LogShipper(post, "stdout", sleep=lambda s: None, max_buffer=3, max_lines=3)
    for i in range(3):
        ship.write(f"l{i}")
    ship.flush()
    assert sent[0] == ["l0", "l1", "l2"]
    later = [text for batch in sent[1:] for text in batch]
    assert [t for t in later if t.startswith("l")] == ["l3", "l4", "l5"]
    assert any("dropped" in t for t in later)

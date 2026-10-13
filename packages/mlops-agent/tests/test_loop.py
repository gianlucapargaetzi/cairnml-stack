import threading

from mlops_agent.config import AgentSettings
from mlops_agent.loop import AgentLoop


class FakeRunner:
    def __init__(self):
        self.ran, self.cancelled, self.gate = [], [], threading.Event()

    def run(self, assignment):
        self.ran.append(assignment.job_id)
        self.gate.wait(5)

    def cancel(self, job_id):
        self.cancelled.append(job_id)
        self.gate.set()


def _loop(api, runner, tmp_path):
    return AgentLoop(api, runner, AgentSettings(home=tmp_path, heartbeat_s=1))


def test_poll_once_runs_assigned_job_in_background(
    server, enroll_client, make_project, new_job, make_agent, tmp_path
):
    from mlops_agent.api import AgentApi

    dev = enroll_client("dev")
    make_project("vision/seg", members=["dev"])
    agent = make_agent()
    api = AgentApi(agent.http)
    runner = FakeRunner()
    loop = _loop(api, runner, tmp_path)
    assert loop.poll_once(wait_s=0) is False
    job = new_job(dev.http)
    assert loop.poll_once(wait_s=0) is True
    for _ in range(100):
        if runner.ran:
            break
        threading.Event().wait(0.02)
    assert runner.ran == [job["id"]] and loop.running_ids() == [job["id"]]
    runner.gate.set()
    for _ in range(100):
        if not loop.running_ids():
            break
        threading.Event().wait(0.02)
    assert loop.running_ids() == []


def test_heartbeat_forwards_cancellations(
    server, enroll_client, make_project, new_job, make_agent, tmp_path
):
    from mlops_agent.api import AgentApi

    dev = enroll_client("dev")
    make_project("vision/seg", members=["dev"])
    agent = make_agent()
    runner = FakeRunner()
    loop = _loop(AgentApi(agent.http), runner, tmp_path)
    job = new_job(dev.http)
    loop.poll_once(wait_s=0)
    dev.http.post(f"/api/v1/jobs/{job['id']}/cancel")
    loop.heartbeat_once()
    assert runner.cancelled == [job["id"]]
    for _ in range(100):
        if not loop.running_ids():
            break
        threading.Event().wait(0.02)


def test_run_forever_stops_cleanly_and_survives_poll_errors(tmp_path):
    class FlakyApi:
        def __init__(self):
            self.calls = 0

        def poll(self, running, wait_s):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("network down")
            return None

        def heartbeat(self, running, capabilities=None, usage=None):
            return []

    api, stop = FlakyApi(), threading.Event()
    loop = AgentLoop(api, FakeRunner(), AgentSettings(home=tmp_path, poll_wait_s=0, heartbeat_s=1))
    loop._sleep = lambda seconds: None
    thread = threading.Thread(target=loop.run_forever, args=(stop,))
    thread.start()
    for _ in range(200):
        if api.calls >= 3:
            break
        threading.Event().wait(0.02)
    stop.set()
    thread.join(10)
    assert api.calls >= 3 and not thread.is_alive()


def test_heartbeat_includes_usage_and_survives_a_failing_sampler(
    server, enroll_client, make_agent, tmp_path
):
    from mlops_agent.api import AgentApi
    from mlops_common.schemas import AgentUsage

    agent = make_agent()
    sent = []
    api = AgentApi(agent.http)
    original = api.heartbeat
    def recording(running, capabilities=None, usage=None):
        sent.append(usage)
        return original(running, capabilities, usage)

    api.heartbeat = recording
    good = lambda: AgentUsage(cpu_percent=10, mem_used_gb=1, mem_total_gb=2)  # noqa: E731
    AgentLoop(api, FakeRunner(), AgentSettings(home=tmp_path), usage_fn=good).heartbeat_once()
    assert sent[-1].cpu_percent == 10

    def broken():
        raise RuntimeError("psutil exploded")

    AgentLoop(api, FakeRunner(), AgentSettings(home=tmp_path), usage_fn=broken).heartbeat_once()
    assert sent[-1] is None

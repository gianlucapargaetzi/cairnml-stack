"""Section 6 of E2E.md: queueing, placement, running, monitoring, ending and recovering jobs.

A job is a recorded task put in the queue with what it needs. The scheduler places it on the agent that fits, the
agent claims it and runs it in a container. Two groups of tests:

- scheduling (no job has to run): what the queue does with a job that fits, does not fit, or is queued twice;
- execution: the job's own run. These need the job containers to start (KNOWN DEFECT D1 in E2E.md), so they are
  strict expected failures until it is fixed. When D1 is fixed, the marker turns them into a failing test
  ("XPASS strict"), and the marker is removed.
"""

import shutil
import tempfile
import time
from pathlib import Path

import pytest

from support import jobs, workspace
from support import agent
from support.agent import AgentMachine, worker_record
from support.workspace import new_name, run_json
from support.defects import DEFECT_FAILURES

pytestmark = pytest.mark.agent

JOB_FOLDER = Path(tempfile.mkdtemp(prefix="e2e-job-script-"))
for _name in ("common.py", "job_script.py"):
    shutil.copy(Path(__file__).parent / "scripts" / _name, JOB_FOLDER / _name)
JOB_SCRIPT = JOB_FOLDER / "job_script.py"

D1 = "KNOWN DEFECT D1 (job launch): the job starts, but the server reports its task as not found, so the agent stops it (see E2E.md, known defects)"
MISSING_IMAGE = "e2e-missing/does-not-exist:never"


@pytest.fixture
def machine(job_agent):
    return job_agent


def make_job(home, project, label, *, scalars=2, extra=()):
    """A job record: the job script, run from a folder outside any git repository (so the agent needs no clone),
    with its arguments."""
    return run_json(home, str(JOB_SCRIPT), ["--project", project, "--name", new_name(label),
                                            "--scalars", str(scalars), *extra])["task_id"]


def events_of(api, task_id):
    events = api.authed("scheduler.get_events", {"limit": 500})["events"]
    return [e for e in events if e.get("task") == task_id]


def wait_for_event(api, task_id, kind, timeout=180):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        found = [e for e in events_of(api, task_id) if e["kind"] == kind]
        if found:
            return found
        time.sleep(3)
    return []


# --- scheduling -------------------------------------------------------------------------------------------------

def test_job_that_no_machine_fits_stays_queued_with_the_reason(client_home, project, machine):
    """The Jobs view (scheduler.get_jobs, state pending) says why a waiting job waits."""
    task_id = make_job(client_home, project, "unfit")
    jobs.enqueue(client_home, task_id, gpus=50)
    api = workspace.device_api(client_home)
    time.sleep(20)
    assert jobs.task_record(api, task_id)["status"] == "queued"
    waiting = api.authed("scheduler.get_jobs", {"state": "pending"})["jobs"]
    entry = next((j for j in waiting if j.get("task") == task_id), None)
    assert entry is not None, "a job that does not fit must be listed as pending"
    assert entry.get("reason"), "a pending job must say why it waits"
    assert not any(e["kind"] == "placed" for e in events_of(api, task_id))


def test_job_that_fits_is_placed_on_the_agent(client_home, project, machine):
    task_id = make_job(client_home, project, "fits")
    jobs.enqueue(client_home, task_id, cpus=1, ram_gb=1, gpus=0, disk_gb=1)
    api = workspace.device_api(client_home)
    placed = wait_for_event(api, task_id, "placed", timeout=120)
    assert placed, "the scheduler must place a job that fits"
    assert placed[0]["worker"] == machine.worker_name


def test_job_placed_on_the_agent_is_claimed_by_it(client_home, project, machine):
    task_id = make_job(client_home, project, "claimed")
    jobs.enqueue(client_home, task_id, cpus=1, ram_gb=1, gpus=0, disk_gb=1)
    api = workspace.device_api(client_home)
    claimed = wait_for_event(api, task_id, "claimed", timeout=180)
    assert claimed and claimed[0]["worker"] == machine.worker_name


def test_enqueueing_a_queued_task_again_leaves_it_queued_once(client_home, project, machine):
    """Enqueueing a task that is already queued is accepted and changes nothing: it is still queued, once."""
    task_id = make_job(client_home, project, "twice")
    jobs.enqueue(client_home, task_id, gpus=50)
    again = workspace.run_raw(client_home, "enqueue.py", ["--task-id", task_id, "--gpus", "50"])
    assert again.returncode == 0, again.output
    api = workspace.device_api(client_home)
    assert jobs.task_record(api, task_id)["status"] == "queued"
    pending = [j for j in api.authed("scheduler.get_jobs", {"state": "pending"})["jobs"] if j.get("task") == task_id]
    assert len(pending) == 1


@pytest.mark.xfail(strict=True, raises=DEFECT_FAILURES, reason="KNOWN DEFECT D6: after any service call, enqueue is refused as 'upgrade "
                   "clearml-server' (the SDK's API level is lowered by api_proxy); enqueue works only as the first call")
def test_enqueue_works_after_the_task_was_read(client_home, project, machine):
    task_id = make_job(client_home, project, "after-get")
    result = workspace.run_raw(client_home, "enqueue_after_get.py", ["--task-id", task_id])
    assert result.returncode == 0, result.output[-400:]


def test_job_with_a_missing_image_fails_once_and_is_not_rescheduled(client_home, project, machine):
    """An internal failure (the image cannot be pulled) is reported as failed; only a lost attempt is retried."""
    task_id = make_job(client_home, project, "missing-image", extra=("--base-image", MISSING_IMAGE))
    api = workspace.device_api(client_home)
    workspace.run_raw(client_home, "enqueue.py", ["--task-id", task_id, "--force"])
    record = jobs.wait_for(api, task_id, jobs.FINAL, timeout=300)
    assert record["status"] == "failed"
    assert not [e for e in events_of(api, task_id) if e["kind"] == "retried"]


def _schedulable(api, worker_name):
    """What the agent can hand to jobs: its capacity less what it keeps for the host."""
    record = worker_record(api, worker_name)
    capacity, reserved = record["capacity"], record["reserved"]
    return {"cpus": int(capacity["cpus"] - reserved["cpus"]),
            "ram_gb": round((capacity["ram_gb"] - reserved["ram_gb"]) * 0.9, 1),
            "disk_gb": round((capacity["disk_gb"] - reserved["disk_gb"]) * 0.5, 1)}


def test_higher_priority_job_is_placed_before_a_lower_one(client_home, project, machine):
    """Deterministic: a first job takes the whole schedulable capacity, so the two that follow cannot both fit.
    When the first job ends (it releases the capacity), the scheduler must place the higher priority one first."""
    api = workspace.device_api(client_home)
    free = _schedulable(api, machine.worker_name)
    holder = make_job(client_home, project, "holder", scalars=1, extra=("--sleep", "60"))
    jobs.enqueue(client_home, holder, **free)
    assert wait_for_event(api, holder, "placed", timeout=180), "the holder must take the whole machine"

    low = make_job(client_home, project, "low-priority")
    high = make_job(client_home, project, "high-priority")
    jobs.enqueue(client_home, low, priority=10, **free)
    jobs.enqueue(client_home, high, priority=90, **free)
    high_placed = wait_for_event(api, high, "placed", timeout=900)
    low_placed = wait_for_event(api, low, "placed", timeout=900)
    assert high_placed and low_placed
    assert high_placed[0]["time"] <= low_placed[0]["time"], "the higher priority job must be placed first"


# --- execution (blocked by D1) ----------------------------------------------------------------------------------

@pytest.mark.xfail(strict=True, raises=DEFECT_FAILURES, reason=D1)
def test_job_runs_to_completion_with_its_scalars_and_artifact(client_home, project, machine):
    task_id = make_job(client_home, project, "completes", scalars=5)
    jobs.enqueue(client_home, task_id)
    api = workspace.device_api(client_home)
    record = jobs.wait_for(api, task_id, jobs.FINAL, timeout=300)
    assert record["status"] == "completed", record.get("status_message")
    assert "result" in [a["key"] for a in record["execution"]["artifacts"]]


@pytest.mark.xfail(strict=True, raises=DEFECT_FAILURES, reason=D1)
def test_failing_job_is_failed_with_its_traceback_and_the_agent_is_free(client_home, project, machine):
    task_id = make_job(client_home, project, "fails", scalars=5, extra=("--fail-after", "2"))
    jobs.enqueue(client_home, task_id)
    api = workspace.device_api(client_home)
    record = jobs.wait_for(api, task_id, jobs.FINAL, timeout=300)
    assert record["status"] == "failed"
    assert "deliberate failure" in workspace.device_api(client_home).authed(
        "events.get_task_log", {"task": task_id, "order": "desc"})["events"][0]["msg"]


@pytest.mark.xfail(strict=True, raises=DEFECT_FAILURES, reason=D1)
def test_aborted_job_stops_within_thirty_seconds(client_home, project, machine):
    """The job must really be running before it is aborted: its first scalar is logged, and that happens only
    once the job body has started (a claimed job whose process never starts logs nothing)."""
    task_id = make_job(client_home, project, "aborted", scalars=1, extra=("--sleep", "600"))
    jobs.enqueue(client_home, task_id)
    api = workspace.device_api(client_home)
    running = jobs.wait_until(api, task_id, lambda r: r.get("last_metrics"), timeout=300)
    assert running, "the job body must have started (its first scalar is logged) before it can be aborted"
    api.authed("tasks.stop", {"task": task_id, "force": True})
    stopped_at = time.monotonic()
    record = jobs.wait_for(api, task_id, ("aborted", "stopped"), timeout=60)
    assert time.monotonic() - stopped_at <= 30
    assert record["status"] in ("aborted", "stopped")


@pytest.mark.xfail(strict=True, raises=DEFECT_FAILURES, reason=D1)
def test_lost_agent_during_a_job_retries_the_job_once(client_home, project, tmp_path_factory, admin_account):
    machine = AgentMachine(tmp_path_factory.mktemp("lost-job-agent"), worker_name=new_name("lost-agent"))
    assert agent.init(machine.home, admin_account).returncode == 0
    machine.start()
    api = workspace.device_api(client_home)
    try:
        assert machine.wait_until(lambda: worker_record(api, machine.worker_name), timeout=240)
        task_id = make_job(client_home, project, "lost", scalars=1, extra=("--sleep", "300"))
        jobs.enqueue(client_home, task_id)
        assert jobs.wait_until(api, task_id, lambda r: r.get("status") == "in_progress", timeout=300)
    finally:
        machine.stop()
    assert wait_for_event(api, task_id, "retried", timeout=180), "the lost attempt must be retried once"


@pytest.mark.xfail(strict=True, raises=DEFECT_FAILURES, reason=D1)
def test_agent_reports_no_running_job_once_a_job_completes(client_home, project, machine):
    """Only a job that completed proves the agent released it: an empty list after a failure proves nothing."""
    task_id = make_job(client_home, project, "release", scalars=1)
    jobs.enqueue(client_home, task_id)
    api = workspace.device_api(client_home)
    record = jobs.wait_for(api, task_id, jobs.FINAL, timeout=300)
    assert record["status"] == "completed", record.get("status_message")
    assert worker_record(api, machine.worker_name)["jobs"] == []

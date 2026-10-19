"""Section 6 of E2E.md: queueing, placement, running, monitoring, ending and recovering jobs.

A job is a recorded task put in the queue with what it needs. The scheduler places it on the agent that fits, the
agent claims it and runs it in a container. Two groups of tests: scheduling (what the queue does with a job) and
execution (the job's own run). A test that fails because of a known defect fails, and its docstring names the defect.
"""

import json
import shutil
import tempfile
import time
from pathlib import Path

import pytest

from support import cli, jobs, workspace
from support.agent import LOST_WITHIN_SEC, worker_record
from support.workspace import new_name

pytestmark = [pytest.mark.agent, pytest.mark.xdist_group("agent")]

JOB_FOLDER = Path(tempfile.mkdtemp(prefix="e2e-job-script-"))
for _name in ("common.py", "job_script.py"):
    shutil.copy(Path(__file__).parent / "scripts" / _name, JOB_FOLDER / _name)
JOB_SCRIPT = JOB_FOLDER / "job_script.py"

MISSING_IMAGE = "e2e-missing/does-not-exist:never"
EVENT_TIMEOUT = 60


@pytest.fixture
def machine(job_agent):
    return job_agent


# The job records of this module, by label: each one's arguments (the scalars default to 2).
JOB_SPECS = {
    "unfit": [], "fits": [], "claimed": [], "twice": [], "after-get": [],
    "missing-image": ["--base-image", MISSING_IMAGE],
    "holder": ["--scalars", "1", "--sleep", "15"],
    "low-priority": [], "high-priority": [],
    "completes": ["--scalars", "5"],
    "fails": ["--scalars", "5", "--fail-after", "2"],
    "aborted": ["--scalars", "1", "--sleep", "600"],
    "lost": ["--scalars", "1", "--sleep", "300"],
    "release": ["--scalars", "1"],
}
DEFAULT_ARGS = ["--scalars", "2"]


@pytest.fixture(scope="module")
def recorded(client_home, project, tmp_path_factory):
    """The records of this module's jobs, made in one process (E2E.md, speed section, item 12). Each record has its own
    arguments; the body runs on the agent with them.

    Expect: every job of the module is recorded in the project, with the arguments its test needs.
    """
    folder = tmp_path_factory.mktemp("job-records")
    labels = list(JOB_SPECS)
    entries = [{"argv": ["--project", project, "--name", new_name(label), *DEFAULT_ARGS, *JOB_SPECS[label]]}
               for label in labels]
    (folder / "jobs.json").write_text(json.dumps(entries))
    result = cli.python(JOB_SCRIPT, client_home, args=["--batch", folder / "jobs.json"], timeout=300)
    assert result.returncode == 0, result.output[-3000:]
    reports = [json.loads(line) for line in result.stdout.splitlines() if line.startswith('{"')]
    assert len(reports) == len(labels), result.output[-3000:]
    return {label: report["task_id"] for label, report in zip(labels, reports)}


def events_of(api, task_id):
    events = api.authed("scheduler.get_events", {"limit": 500})["events"]
    return [e for e in events if e.get("task") == task_id]


def wait_for_event(api, task_id, kind, timeout=EVENT_TIMEOUT):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        found = [e for e in events_of(api, task_id) if e["kind"] == kind]
        if found:
            return found
        time.sleep(1)
    return []


def wait_for_pending(api, task_id, timeout=10):
    """The pending entry of a job, once the scheduler has looked at it."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        entry = next((j for j in api.authed("scheduler.get_jobs", {"state": "pending"})["jobs"]
                      if j.get("task") == task_id), None)
        if entry:
            return entry
        time.sleep(1)
    return None


# --- scheduling -------------------------------------------------------------------------------------------------

def test_job_that_no_machine_fits_stays_queued_with_the_reason(client_home, project, machine, recorded):
    """The Jobs view (scheduler.get_jobs, state pending) says why a waiting job waits.

    Expect: a job that needs a GPU the machine does not have stays queued, is listed as pending with a reason, and is
    never placed.
    """
    task_id = recorded["unfit"]
    jobs.enqueue(client_home, task_id, gpus=50)
    api = workspace.device_api(client_home)
    entry = wait_for_pending(api, task_id)
    assert entry is not None, "a job that does not fit must be listed as pending"
    assert jobs.task_record(api, task_id)["status"] == "queued"
    assert entry.get("reason"), "a pending job must say why it waits"
    assert not any(e["kind"] == "placed" for e in events_of(api, task_id))


def test_job_that_fits_is_placed_on_the_agent(client_home, project, machine, recorded):
    """A job that fits is placed on the agent.

    Expect: a job whose needs the agent meets is placed on that agent by the scheduler."""
    task_id = recorded["fits"]
    jobs.enqueue(client_home, task_id, cpus=1, ram_gb=1, gpus=0, disk_gb=1)
    api = workspace.device_api(client_home)
    placed = wait_for_event(api, task_id, "placed")
    assert placed, "the scheduler must place a job that fits"
    assert placed[0]["worker"] == machine.worker_name


def test_job_placed_on_the_agent_is_claimed_by_it(client_home, project, machine, recorded):
    """The agent claims the job it was offered.

    Expect: the agent the job was placed on claims the offer, so the job is handed to it and not to another."""
    task_id = recorded["claimed"]
    jobs.enqueue(client_home, task_id, cpus=1, ram_gb=1, gpus=0, disk_gb=1)
    api = workspace.device_api(client_home)
    claimed = wait_for_event(api, task_id, "claimed")
    assert claimed and claimed[0]["worker"] == machine.worker_name


def test_enqueueing_a_queued_task_again_leaves_it_queued_once(client_home, project, machine, recorded):
    """Enqueueing a task that is already queued is accepted and changes nothing: it is still queued, once.

    Expect: a second enqueue succeeds, the task stays queued, and it appears once in the pending list.
    """
    task_id = recorded["twice"]
    jobs.enqueue(client_home, task_id, gpus=50)
    again = workspace.run_raw(client_home, "enqueue.py", ["--task-id", task_id, "--gpus", "50"])
    assert again.returncode == 0, again.output
    api = workspace.device_api(client_home)
    assert jobs.task_record(api, task_id)["status"] == "queued"
    pending = [j for j in api.authed("scheduler.get_jobs", {"state": "pending"})["jobs"] if j.get("task") == task_id]
    assert len(pending) == 1


def test_enqueue_works_after_the_task_was_read(client_home, project, machine, recorded):
    """Enqueueing after the task was read over the API still works (defect D6 would refuse it).

    Expect: the enqueue succeeds in a process that first reads the task.
    """
    task_id = recorded["after-get"]
    result = workspace.run_raw(client_home, "enqueue_after_get.py", ["--task-id", task_id])
    assert result.returncode == 0, result.output[-400:]


def test_job_with_a_missing_image_fails_once_and_is_not_rescheduled(client_home, project, machine, recorded):
    """An internal failure (the image cannot be pulled) is reported as failed; only a lost attempt is retried.

    Expect: the job ends as failed, after one attempt, with no retry event.
    """
    task_id = recorded["missing-image"]
    api = workspace.device_api(client_home)
    workspace.run_raw(client_home, "enqueue.py", ["--task-id", task_id, "--force"])
    record = jobs.wait_for(api, task_id, jobs.FINAL)
    assert record["status"] == "failed"
    assert not [e for e in events_of(api, task_id) if e["kind"] == "retried"]


def _schedulable(api, worker_name):
    """What the agent can hand to jobs: its capacity less what it keeps for the host."""
    record = worker_record(api, worker_name)
    capacity, reserved = record["capacity"], record["reserved"]
    return {"cpus": int(capacity["cpus"] - reserved["cpus"]),
            "ram_gb": round((capacity["ram_gb"] - reserved["ram_gb"]) * 0.9, 1),
            "disk_gb": round((capacity["disk_gb"] - reserved["disk_gb"]) * 0.5, 1)}


def test_higher_priority_job_is_placed_before_a_lower_one(client_home, project, machine, recorded):
    """Deterministic: a first job takes the whole schedulable capacity, so the two that follow cannot both fit.
    When the first job ends (it releases the capacity), the scheduler must place the higher priority one first.

    Expect: when capacity frees up, the job with the higher priority is placed before the one with the lower priority.
    """
    api = workspace.device_api(client_home)
    free = _schedulable(api, machine.worker_name)
    # the holder's body runs for 15 s on the agent: long enough for the two below to be queued while it holds the machine
    holder = recorded["holder"]
    jobs.enqueue(client_home, holder, **free)
    assert wait_for_event(api, holder, "placed"), "the holder must take the whole machine"

    low = recorded["low-priority"]
    high = recorded["high-priority"]
    jobs.enqueue(client_home, low, priority=10, **free)
    jobs.enqueue(client_home, high, priority=90, **free)
    high_placed = wait_for_event(api, high, "placed")
    low_placed = wait_for_event(api, low, "placed")
    assert high_placed and low_placed
    assert high_placed[0]["time"] <= low_placed[0]["time"], "the higher priority job must be placed first"


# --- execution ----------------------------------------------------------------------------------

def test_job_runs_to_completion_with_its_scalars_and_artifact(client_home, project, machine, recorded):
    """A job runs to completion, with its scalars and artifact.

    Expect: the job completes on the agent, its scalars are kept, and its result artifact is on the task."""
    task_id = recorded["completes"]
    jobs.enqueue(client_home, task_id)
    api = workspace.device_api(client_home)
    # the first job of a run starts its container cold: the container installs the agent and the SDK from source, which
    # takes minutes, so it is the one job wait with a longer ceiling. Localhost does not make a package download faster
    # (E2E.md, speed section, item 8).
    record = jobs.wait_for(api, task_id, jobs.FINAL, timeout=300)
    assert record["status"] == "completed", record.get("status_message")
    assert "result" in [a["key"] for a in record["execution"]["artifacts"]]


def test_failing_job_is_failed_with_its_traceback_and_the_agent_is_free(client_home, project, machine, recorded):
    """A failing job, and the agent after it.

    Expect: a job whose body raises ends as failed, its traceback is in the job's log, and the agent is free again.
    """
    task_id = recorded["fails"]
    jobs.enqueue(client_home, task_id)
    api = workspace.device_api(client_home)
    record = jobs.wait_for(api, task_id, jobs.FINAL)
    assert record["status"] == "failed"
    # the traceback is printed just before the agent's own "Process failed" line: look through the last events
    recent = workspace.device_api(client_home).authed(
        "events.get_task_log", {"task": task_id, "order": "desc", "size": 50})["events"]
    assert any("deliberate failure" in event["msg"] for event in recent), "the traceback must be in the job's log"


def test_aborted_job_stops_within_thirty_seconds(client_home, project, machine, recorded):
    """The job must really be running before it is aborted: its first scalar is logged, and that happens only
    once the job body has started (a claimed job whose process never starts logs nothing).

    Expect: after the abort, the job ends as aborted or stopped within 30 s.
    """
    task_id = recorded["aborted"]
    jobs.enqueue(client_home, task_id)
    api = workspace.device_api(client_home)
    jobs.wait_for_start(api, task_id)
    api.authed("tasks.stop", {"task": task_id, "force": True})
    stopped_at = time.monotonic()
    record = jobs.wait_for(api, task_id, ("aborted", "stopped"))
    assert time.monotonic() - stopped_at <= 30
    assert record["status"] in ("aborted", "stopped")


def test_lost_agent_during_a_job_retries_the_job_once(client_home, project, machine, recorded):
    """The agent that runs the job is lost while the job runs. The scheduler retries the job once.

    The job runs on the session's agent (the only one this module starts), so the test knows which agent to lose. The
    agent is started again afterwards, for the tests that follow. The lost worker is found by the scheduler's own
    sweep (E2E.md, speed section, item 3): no other job is needed to make a placement pass run.

    Expect: once the agent stops syncing, its worker is marked lost and the job is queued again (one retry), and the
    job runs again when the agent is back.
    """
    api = workspace.device_api(client_home)
    task_id = recorded["lost"]
    jobs.enqueue(client_home, task_id)
    jobs.wait_for_start(api, task_id)
    placed = wait_for_event(api, task_id, "placed")
    assert placed and placed[0]["worker"] == machine.worker_name, "the job must run on the agent the test loses"
    try:
        machine.stop()
        lost = machine.wait_until(lambda: (worker_record(api, machine.worker_name) or {}).get("state") == "lost",
                                  timeout=LOST_WITHIN_SEC)
        assert lost, "the stopped agent must be marked lost by the scheduler's sweep"
        assert wait_for_event(api, task_id, "retried"), "the lost attempt must be retried once"
    finally:
        machine.start()
        assert machine.wait_until(lambda: (worker_record(api, machine.worker_name) or {}).get("state") == "active",
                                  timeout=EVENT_TIMEOUT), "the agent must come back for the tests that follow"


def test_agent_reports_no_running_job_once_a_job_completes(client_home, project, machine, recorded):
    """Only a job that completed proves the agent released it: an empty list after a failure proves nothing.

    Expect: after the job completes, the agent reports no running job.
    """
    task_id = recorded["release"]
    jobs.enqueue(client_home, task_id)
    api = workspace.device_api(client_home)
    record = jobs.wait_for(api, task_id, jobs.FINAL)
    assert record["status"] == "completed", record.get("status_message")
    assert machine.wait_until(lambda: worker_record(api, machine.worker_name)["jobs"] == [], timeout=30), \
        "the agent must report no running job once the job has completed"

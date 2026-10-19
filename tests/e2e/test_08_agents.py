"""Section 5 of E2E.md: enrolling an agent machine, its registration and resources, heartbeat and recovery.

The agent is a real managed daemon on this machine, running in its own HOME with its own device key. Its
resources are checked against the host's own counts. Jobs are section 6 (test_09_jobs.py).
"""

import os
import re
import shutil
import subprocess
import time

import pytest

from support import workspace
from support import agent
from support.agent import AgentMachine, worker_record
from support import jobs
from support.workspace import new_name, run_json

pytestmark = pytest.mark.agent

LOST_AFTER_SEC = 3 * 10 + 30  # three missed syncs of 10 s, with margin for the server's sweep


@pytest.fixture(scope="module")
def machine(tmp_path_factory, admin_account, client_home):
    machine = AgentMachine(tmp_path_factory.mktemp("agent-home"), worker_name=new_name("agent"))
    result = agent.init(machine.home, admin_account)
    assert result.returncode == 0, result.output
    machine.start()
    api = workspace.device_api(client_home)
    online = machine.wait_until(lambda: worker_record(api, machine.worker_name), timeout=240)
    assert online, f"the agent never registered; its log ends:\n{machine.log()[-3000:]}"
    yield machine
    machine.stop()


def test_admin_enrols_the_agent_machine_with_its_own_key(machine):
    assert machine.key_path.exists(), "the agent's device key must be written"
    assert machine.device_id.startswith("dev_")
    assert oct(os.stat(machine.key_path).st_mode & 0o777) == "0o600"


def test_agent_device_is_kind_agent(client_home, machine):
    api = workspace.device_api(client_home)
    devices = api.authed("devices.get_all", {})["devices"]
    mine = next(d for d in devices if d["id"] == machine.device_id)
    assert mine["kind"] == "agent"
    assert mine["revoked"] is False


def test_member_cannot_enrol_an_agent(member_account, tmp_path):
    """Only an admin may enrol an agent, because it runs other people's code."""
    machine = AgentMachine(tmp_path / "member-agent", worker_name="e2e-refused")
    machine.home.mkdir()
    result = agent.init(machine.home, member_account)
    assert "only an admin" in result.output or "not enrolled" in result.output, result.output
    assert not machine.key_path.exists()
    assert not (machine.home / "clearml.conf").exists() or "device_id" not in (
        machine.home / "clearml.conf").read_text()


def test_agent_registers_as_a_worker_with_its_host_resources(client_home, machine):
    api = workspace.device_api(client_home)
    record = worker_record(api, machine.worker_name)
    assert record["state"] == "active"
    capacity = record["capacity"]
    assert capacity["cpus"] == os.cpu_count()
    mem_gb = _host_memory_gb()
    assert abs(capacity["ram_gb"] - mem_gb) / mem_gb < 0.05, (capacity["ram_gb"], mem_gb)
    assert len(capacity.get("gpus", [])) == _host_gpu_count()


def test_agent_keeps_a_share_of_the_machine_for_the_host(client_home, machine):
    record = worker_record(workspace.device_api(client_home), machine.worker_name)
    reserved = record["reserved"]
    assert reserved["cpus"] >= 1
    assert reserved["ram_gb"] > 0


def test_agent_reports_its_usage(client_home, machine):
    api = workspace.device_api(client_home)
    usage = machine.wait_until(lambda: (worker_record(api, machine.worker_name) or {}).get("usage"), timeout=120)
    assert usage, "the agent must report its usage at each sync"
    assert 0 <= usage["cpu_percent"] <= 100 * os.cpu_count()
    assert 0 < usage["ram_used_gb"] <= _host_memory_gb()
    assert 0 <= usage["disk_used_percent"] <= 100


def test_agent_without_its_key_does_not_register(tmp_path, admin_account, client_home):
    """A machine whose device key is gone cannot sign in, so it never appears as a worker."""
    machine = AgentMachine(tmp_path / "keyless", worker_name=new_name("keyless"))
    assert agent.init(machine.home, admin_account).returncode == 0
    machine.key_path.unlink()
    machine.start()
    try:
        time.sleep(30)  # a negative check: the agent must stay unregistered for the whole window
        api = workspace.device_api(client_home)
        assert worker_record(api, machine.worker_name) is None
        assert "device.key" in machine.log() or "enrol" in machine.log().lower(), machine.log()[-2000:]
    finally:
        machine.stop()


def test_agent_without_its_key_says_to_enrol_it(tmp_path, admin_account):
    machine = AgentMachine(tmp_path / "keyless-msg", worker_name=new_name("keyless-msg"))
    assert agent.init(machine.home, admin_account).returncode == 0
    machine.key_path.unlink()
    machine.start()
    try:
        machine.wait_until(lambda: "device.key" in machine.log() or "enrol" in machine.log().lower(), timeout=60, poll=2)
        assert "clearml-agent init" in machine.log()
    finally:
        machine.stop()


def test_stopped_agent_is_lost_once_a_scheduler_pass_runs_and_returns_without_enrolling(client_home, machine,
                                                                                    project):
    """The heartbeat timeout marks the agent lost when the scheduler runs a pass. A task that cannot fit anywhere
    makes the pass run; the agent then comes back on its own, with the same device."""
    device_before = machine.device_id
    key_before = machine.key_path.read_bytes()
    api = workspace.device_api(client_home)
    machine.stop()
    time.sleep(LOST_AFTER_SEC)  # the agent must be stale before the pass, or the pass finds it still in time

    unfit = run_json(client_home, "job_script.py", ["--project", project, "--name", new_name("unfit"),
                                                    "--scalars", "1"])
    jobs.enqueue(client_home, unfit["task_id"], gpus=50)
    lost = machine.wait_until(lambda: (worker_record(api, machine.worker_name) or {}).get("state") == "lost",
                            timeout=LOST_AFTER_SEC + 120, poll=5)
    assert lost, "the pass must mark the stopped agent lost"

    machine.start()
    back = machine.wait_until(lambda: (worker_record(api, machine.worker_name) or {}).get("state") == "active",
                            timeout=240)
    assert back, "the agent must come back online by itself"
    assert machine.device_id == device_before, "coming back must not enrol the machine again"
    assert machine.key_path.read_bytes() == key_before


def _host_memory_gb() -> float:
    with open("/proc/meminfo", encoding="utf-8") as handle:
        kib = int(re.search(r"MemTotal:\s+(\d+) kB", handle.read()).group(1))
    return kib / (1024 * 1024)


def _host_gpu_count() -> int:
    if not shutil.which("nvidia-smi"):
        return 0
    out = subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True, timeout=30)
    return sum(1 for line in out.stdout.splitlines() if line.startswith("GPU "))

"""Section 5 of E2E.md, heartbeat on its own: a stopped agent and the scheduler's lost-worker rule.

This module runs one agent and nothing else that calls the scheduler, so what it sees is the server's rule and
not the activity of other machines. The rule is driven by scheduler activity (see E2E.md, known defects).
"""

import pytest

from support import workspace
from support import agent
from support.agent import AgentMachine, worker_record
from support.workspace import new_name

pytestmark = pytest.mark.agent

LOST_AFTER_SEC = 3 * 10 + 30


def test_stopped_agent_is_marked_lost_by_the_timeout_alone(tmp_path, admin_account, client_home):
    machine = AgentMachine(tmp_path / "timeout-only", worker_name=new_name("timeout"))
    assert agent.init(machine.home, admin_account).returncode == 0
    machine.start()
    api = workspace.device_api(client_home)
    try:
        assert machine.wait_until(lambda: worker_record(api, machine.worker_name), timeout=240)
    finally:
        machine.stop()
    lost = machine.wait_until(
        lambda: (worker_record(api, machine.worker_name) or {}).get("state") == "lost", timeout=LOST_AFTER_SEC + 60)
    assert lost, "a stopped agent must be marked lost after the heartbeat timeout, without other activity"



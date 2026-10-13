import os
import subprocess

import pytest

pytestmark = pytest.mark.e2e

REPO = os.environ.get("MLOPS_E2E_GITHUB_REPO")
URL = os.environ.get("MLOPS_E2E_GITHUB_REPO_URL")


@pytest.mark.skipif(
    not (REPO and URL), reason="set MLOPS_E2E_GITHUB_REPO and _URL (see docs/e2e-test-repo.md)"
)
def test_a_dirty_local_run_is_reproduced_on_the_agent(
    dev, project, agent_ready, wait_for, tmp_path
):
    work = tmp_path / "checkout"
    subprocess.run(["git", "clone", "-q", URL, str(work)], check=True)
    (work / "bias.txt").write_text(
        "5\n"
    )  # uncommitted change: only the patch can carry it to the agent

    local = dev.python(work / "train.py", "--steps", "3", cwd=work)
    assert local.returncode == 0, local.stderr
    api = dev.api()
    exp = next(
        e for e in api.list_runs(project) if e["name"] == "repro" and e["source"] == "local"
    )
    assert exp["git"]["dirty"] is True and exp["git"]["repo"] == REPO
    local_series = [
        p["value"]
        for p in api._http.get(f"/api/v1/runs/{exp['id']}/metrics").json()["score"]
    ]
    assert local_series == [5.0, 6.0, 7.0]

    out = dev.run("dispatch", exp["id"], "--cpu", "1", "--memory-gb", "1").stdout
    job_id = next(w for w in out.split() if w.startswith("job_"))
    wait_for(
        lambda: api.get_job(job_id)["status"] in ("finished", "failed"),
        timeout=900,
        message="the remote run",
    )
    job = api.get_job(job_id)
    assert job["status"] == "finished", job

    remote = next(e for e in api.list_runs(project) if e["job_id"] == job_id)
    remote_series = [
        p["value"]
        for p in api._http.get(f"/api/v1/runs/{remote['id']}/metrics").json()["score"]
    ]
    assert remote_series == local_series  # same commit, same patch, same environment, same result
    texts = [line["text"] for c in api.get_logs(remote["id"]) for line in c["lines"]]
    assert "bias=5.0 steps=3" in texts

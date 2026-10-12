import subprocess

import pytest

pytestmark = pytest.mark.e2e


def _spec(tmp_path, command, name="e2e-image"):
    path = tmp_path / f"{name}.yaml"
    path.write_text(
        f"name: {name}\nproject: e2e/demo\nqueue: default\nresources: {{cpu: 1, memory_gb: 0.5}}\n"
        "runtime:\n  type: image\n  image: alpine:3.20\n  entrypoint: [/bin/sh, -c]\n"
        f"  command: ['{command}']\n"
    )
    return path


def _dispatch(dev, spec):
    out = dev.run("dispatch", "--file", str(spec)).stdout
    return next(w for w in out.split() if w.startswith("job_")), out.split("experiment ")[1].split(
        ")"
    )[0]


def _status(dev, job_id):
    return dev.api().get_job(job_id)["status"]


def test_image_job_runs_on_the_agent_and_logs_come_back(
    dev, project, agent_ready, wait_for, tmp_path
):
    job_id, exp_id = _dispatch(dev, _spec(tmp_path, "echo hello-from-job; echo to-stderr 1>&2"))
    wait_for(
        lambda: _status(dev, job_id) in ("finished", "failed"),
        timeout=180,
        message="the job to end",
    )
    assert _status(dev, job_id) == "finished"
    api = dev.api()
    streams = {}
    for chunk in api.get_logs(exp_id):
        streams.setdefault(chunk["stream"], []).extend(line["text"] for line in chunk["lines"])
    assert "hello-from-job" in streams["stdout"] and "to-stderr" in streams["stderr"]
    assert api.get_experiment(exp_id)["status"] == "finished"


def test_failing_job_is_reported_failed_with_its_exit_code(
    dev, project, agent_ready, wait_for, tmp_path
):
    job_id, _ = _dispatch(dev, _spec(tmp_path, "exit 3", "e2e-fail"))
    wait_for(
        lambda: _status(dev, job_id) in ("finished", "failed"),
        timeout=180,
        message="the job to end",
    )
    job = dev.api().get_job(job_id)
    assert job["status"] == "failed" and job["exit_code"] == 3


def test_a_running_job_can_be_cancelled_and_its_container_disappears(
    dev, project, agent_ready, wait_for, tmp_path
):
    job_id, _ = _dispatch(dev, _spec(tmp_path, "sleep 600", "e2e-sleep"))
    wait_for(lambda: _status(dev, job_id) == "running", timeout=180, message="the job to start")
    dev.run("job", "cancel", job_id)
    wait_for(
        lambda: _status(dev, job_id) == "cancelled", timeout=120, message="the job to be cancelled"
    )

    def gone():
        out = subprocess.run(
            ["docker", "ps", "-q", "--filter", f"label=mlops.job={job_id}"],
            capture_output=True,
            text=True,
        ).stdout
        return out.strip() == ""

    wait_for(gone, timeout=60, message="the job container to be removed")


def test_jobs_of_a_project_are_invisible_to_non_members(
    make_cli, dev, project, agent_ready, tmp_path
):
    job_id, _ = _dispatch(dev, _spec(tmp_path, "true", "e2e-private"))
    assert dev.run("job", "show", job_id).returncode == 0
    outsider = make_cli("eve")  # a Keycloak user that is not a member of e2e/demo
    assert outsider.run("job", "show", job_id, check=False).returncode == 1
    assert outsider.run("job", "cancel", job_id, check=False).returncode == 1

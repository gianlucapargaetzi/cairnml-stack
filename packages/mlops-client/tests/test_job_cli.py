from mlops.cli import app as cli
from typer.testing import CliRunner


def test_cli_reschedule_with_params(sdk, new_job):
    job = new_job(sdk.dev.http, params={"lr": 0.1, "seed": 7})
    args = ["job", "reschedule", job["id"], "--param", "lr=0.5", "--param", "tag=fast",
            "--unset-param", "seed", "--cpu", "4", "--queue", "gpu"]
    out = CliRunner().invoke(cli, args)
    assert out.exit_code == 0 and "job_" in out.output
    new_id = next(w for w in out.output.split() if w.startswith("job_"))
    spec = sdk.api.get_job_spec(new_id)
    assert spec["params"] == {"lr": 0.5, "tag": "fast"}
    assert spec["resources"]["cpu"] == 4 and spec["queue"] == "gpu"

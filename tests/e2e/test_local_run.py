import httpx
import pytest

pytestmark = pytest.mark.e2e

SCRIPT = """
import mlops
experiment = mlops.init("e2e/demo", "autolog", {"lr": 0.1})
for step in range(3):
    experiment.log_metric("loss", 1.0 / (step + 1), step)
print("hello from the e2e run")
experiment.upload_artifact("out.txt", obj="artifact body")
"""


def test_a_plain_script_is_logged_as_an_experiment(dev, project, tmp_path):
    script = tmp_path / "run_me.py"
    script.write_text(SCRIPT)
    result = dev.python(script, cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert "hello from the e2e run" in result.stdout  # the user still sees the output

    api = dev.api()
    exp = next(e for e in api.list_experiments(project) if e["name"] == "autolog")
    assert (
        exp["status"] == "finished"
        and exp["config"] == {"lr": 0.1}
        and exp["script"] == "run_me.py"
    )
    series = api._http.get(f"/api/v1/experiments/{exp['id']}/metrics").json()["loss"]
    assert [round(p["value"], 3) for p in series] == [1.0, 0.5, 0.333]
    texts = [line["text"] for c in api.get_logs(exp["id"]) for line in c["lines"]]
    assert "hello from the e2e run" in texts
    artifacts = api.list_artifacts(exp["id"])
    assert {a["name"] for a in artifacts} >= {"out.txt", "run_me.py"}
    out = next(a for a in artifacts if a["name"] == "out.txt")
    url = api._http.get(f"/api/v1/experiments/{exp['id']}/artifacts/{out['id']}/download").json()[
        "url"
    ]
    assert httpx.get(url).text == "artifact body"  # it really went through RustFS

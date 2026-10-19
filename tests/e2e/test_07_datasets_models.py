"""Section 7 of E2E.md: datasets and models, created on one machine and used on another.

Each step runs in its own process, so a dataset or model is only as good as what the server stored.
"""

import pytest

from support import workspace
from support.workspace import new_name, run_json
from support.defects import DEFECT_FAILURES


@pytest.fixture(scope="module")
def dataset(client_home, project, tmp_path_factory):
    work = tmp_path_factory.mktemp("dataset-source")
    made = run_json(client_home, "dataset_make.py", [
        "--project", project, "--name", new_name("dataset"), "--work", str(work),
    ], timeout=1200)
    return {"made": made}


def test_dataset_is_created_and_finalized(dataset):
    assert dataset["made"]["dataset_id"]
    assert dataset["made"]["files"], "the dataset must list the files it was built from"


@pytest.mark.xfail(strict=True, raises=DEFECT_FAILURES, reason="KNOWN DEFECT D4: Dataset.add_files on a finalized dataset raises nothing, "
                   "although the SDK documents a finalized dataset as immutable (datasets/dataset.py)")
def test_finalized_dataset_refuses_new_files(dataset):
    assert dataset["made"]["refused_after_finalize"] is True


def test_second_machine_gets_the_same_files_and_hashes(client_home, dataset, tmp_path):
    fetched = run_json(client_home, "dataset_fetch.py", [
        "--dataset-id", dataset["made"]["dataset_id"], "--out", str(tmp_path / "fetched"),
    ], timeout=1200)
    assert fetched["files"] == dataset["made"]["files"]


def test_dataset_fetch_of_an_unknown_id_fails(client_home, tmp_path):
    result = workspace.run_raw(client_home, "dataset_fetch.py", ["--dataset-id", "0" * 32, "--out",
                                                                  str(tmp_path / "missing")])
    assert result.returncode != 0


@pytest.fixture(scope="module")
def model(client_home, project, tmp_path_factory):
    work = tmp_path_factory.mktemp("model-source")
    published = run_json(client_home, "model_publish.py", [
        "--project", project, "--name", new_name("model"), "--work", str(work),
    ], timeout=900)
    return published


def test_model_is_listed_under_its_run(client_home, model):
    api = workspace.device_api(client_home)
    record = api.authed("tasks.get_by_id", {"task": model["task_id"]})["task"]
    models = record.get("models", {}).get("output", [])
    assert model["model_id"] in [m["model"] for m in models]


def test_model_downloads_intact_on_another_machine(client_home, model):
    fetched = run_json(client_home, "model_fetch.py", ["--model-id", model["model_id"]], timeout=900)
    assert fetched["digest"] == model["digest"]

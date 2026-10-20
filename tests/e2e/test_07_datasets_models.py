"""Section 7 of E2E.md: datasets and models, created on one machine and used on another.

Each step runs in its own process, so a dataset or model is only as good as what the server stored.
"""

import pytest

from support import workspace
from support.workspace import new_name, run_json


@pytest.fixture(scope="module")
def dataset(client_home, project, tmp_path_factory):
    work = tmp_path_factory.mktemp("dataset-source")
    made = run_json(client_home, "dataset_make.py", [
        "--project", project, "--name", new_name("dataset"), "--work", str(work),
    ], timeout=300)
    return {"made": made}


def test_dataset_is_created_and_finalized(dataset):
    """A dataset is created and finalized.

    Expect: The dataset has an id, and it lists the files it was built from.
    """
    assert dataset["made"]["dataset_id"]
    assert dataset["made"]["files"], "the dataset must list the files it was built from"


def test_finalized_dataset_refuses_new_files(dataset):
    """A finalized dataset refuses new files.

    Expect: Adding files after the dataset is finalized is refused. Known open defect D4 makes this test fail.
    """
    assert dataset["made"]["refused_after_finalize"] is True


def test_second_machine_gets_the_same_files_and_hashes(client_home, dataset, tmp_path):
    """A second machine gets the same files and hashes.

    Expect: The files fetched on another machine equal the dataset's list, names and hashes.
    """
    fetched = run_json(client_home, "dataset_fetch.py", [
        "--dataset-id", dataset["made"]["dataset_id"], "--out", str(tmp_path / "fetched"),
    ], timeout=300)
    assert fetched["files"] == dataset["made"]["files"]


def test_dataset_fetch_of_an_unknown_id_fails(client_home, tmp_path):
    """Fetching an unknown dataset fails.

    Expect: The fetch exits with a non-zero code.
    """
    result = workspace.run_raw(client_home, "dataset_fetch.py", ["--dataset-id", "0" * 32, "--out",
                                                                  str(tmp_path / "missing")])
    assert result.returncode != 0


@pytest.fixture(scope="module")
def model(client_home, project, tmp_path_factory):
    work = tmp_path_factory.mktemp("model-source")
    published = run_json(client_home, "model_publish.py", [
        "--project", project, "--name", new_name("model"), "--work", str(work),
    ], timeout=300)
    return published


def test_model_is_listed_under_its_run(client_home, model):
    """A model is listed under the run that produced it.

    Expect: The run's output models include the published model.
    """
    api = workspace.device_api(client_home)
    record = api.authed("tasks.get_by_id", {"task": model["task_id"]})["task"]
    models = record.get("models", {}).get("output", [])
    assert model["model_id"] in [m["model"] for m in models]


def test_model_downloads_intact_on_another_machine(client_home, model):
    """A model downloads intact on another machine.

    Expect: The digest of the downloaded model equals the digest it was published with.
    """
    fetched = run_json(client_home, "model_fetch.py", ["--model-id", model["model_id"]], timeout=300)
    assert fetched["digest"] == model["digest"]

import pytest
from mlops_server.models import Experiment, Project
from mlops_server.services.experiments import get_or_create_experiment, guess_kind
from sqlalchemy import select


@pytest.fixture
def dev(enroll_client, make_project):
    dev = enroll_client("dev")
    make_project("vision/seg", members=["dev"])
    return dev


def _run(http, **extra):
    return http.post("/api/v1/runs", json={"project": "vision/seg", "name": "e", **extra})


def test_the_default_experiment_is_created_on_first_use(server, dev):
    body = _run(dev.http).json()
    assert body["experiment"] == "general"
    experiments = dev.http.get("/api/v1/experiments", params={"project": "vision/seg"}).json()
    assert [(t["name"], t["kind"]) for t in experiments] == [("general", "other")]


def test_a_named_experiment_is_created_once_and_runs_share_it(server, dev):
    first = _run(
        dev.http, experiment="training", primary_metric="val_loss", direction="min"
    ).json()
    second = _run(
        dev.http, experiment="training", primary_metric="other", direction="max"
    ).json()
    assert first["experiment"] == second["experiment"] == "training"
    experiments = dev.http.get("/api/v1/experiments", params={"project": "vision/seg"}).json()
    training = next(t for t in experiments if t["name"] == "training")
    assert training["kind"] == "training"  # guessed from the name
    # later runs do not overwrite the metric
    assert (training["primary_metric"], training["direction"]) == ("val_loss", "min")
    assert len([t for t in experiments if t["name"] == "training"]) == 1


@pytest.mark.parametrize("name,kind", [
    ("training", "training"), ("model-train-v2", "training"), ("augment", "augmentation"),
    ("unit-tests", "testing"), ("evaluate", "evaluation"), ("compile-onnx", "compilation"),
    ("prepare-data", "data-preparation"), ("inference", "inference"), ("misc", "other"),
])
def test_kind_is_guessed_from_the_name(name, kind):
    assert guess_kind(name) == kind


def test_experiment_names_are_validated(server, dev):
    for bad in ["Training", "has space", "-x", "a" * 65, ""]:
        assert _run(dev.http, experiment=bad).status_code == 422


def test_experiments_api_create_patch_and_access(server, dev, enroll_client):
    created = dev.http.post(
        "/api/v1/experiments",
        json={"project": "vision/seg", "name": "compile", "kind": "compilation"},
    )
    assert created.status_code == 200 and created.json()["kind"] == "compilation"
    again = dev.http.post("/api/v1/experiments", json={"project": "vision/seg", "name": "compile"})
    assert again.status_code == 409
    experiment_id = created.json()["id"]
    patched = dev.http.patch(
        f"/api/v1/experiments/{experiment_id}",
        json={"description": "to ONNX", "primary_metric": "latency", "direction": "min"},
    )
    assert patched.json()["description"] == "to ONNX"
    assert patched.json()["primary_metric"] == "latency"
    sideways = dev.http.patch(
        f"/api/v1/experiments/{experiment_id}", json={"direction": "sideways"}
    )
    assert sideways.status_code == 422
    eve = enroll_client("eve")
    assert eve.http.get(f"/api/v1/experiments/{experiment_id}").status_code == 404
    patch = eve.http.patch(f"/api/v1/experiments/{experiment_id}", json={"description": "x"})
    assert patch.status_code == 404
    listed = eve.http.get("/api/v1/experiments", params={"project": "vision/seg"})
    assert listed.status_code == 404


def test_dispatch_puts_the_job_into_its_experiment(server, dev, new_job):
    job = new_job(dev.http, experiment="training")
    exp = dev.http.get(f"/api/v1/runs/{job['run_id']}").json()
    assert exp["experiment"] == "training"


def test_a_concurrent_creation_reuses_the_row(app, dev):
    with app.state.session_factory() as session:
        project = session.scalar(select(Project).where(Project.slug == "vision/seg"))
        session.add(
            Experiment(id="exp_winner", project_id=project.id, name="training", kind="training")
        )
        session.commit()
    with app.state.session_factory() as session:
        project = session.scalar(select(Project).where(Project.slug == "vision/seg"))
        real_scalar, lookups = session.scalar, []

        def first_lookup_misses(statement, *args, **kwargs):
            # the other request's row was not visible to this lookup yet
            lookups.append(statement)
            return None if len(lookups) == 1 else real_scalar(statement, *args, **kwargs)

        session.scalar = first_lookup_misses
        experiment = get_or_create_experiment(session, project.id, "training", "val_loss", "min")
        assert experiment.id == "exp_winner" and len(lookups) == 2

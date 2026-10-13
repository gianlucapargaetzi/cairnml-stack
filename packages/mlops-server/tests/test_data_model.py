"""Constraints of the Phase 2 tables: tags, sequences, bookmarks and metric series."""

from __future__ import annotations

import pytest
from mlops_server.models import (
    ExplorerState,
    MetricSeries,
    Project,
    RunTag,
    Sequence,
    SequenceItem,
    Tag,
    User,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError


def _ids(app):
    with app.state.session_factory() as session:
        project = session.scalar(select(Project).where(Project.slug == "vision/seg"))
        user = session.scalar(select(User).where(User.username == "dev"))
        return project.id, user.id


@pytest.fixture
def seeded(server, enroll_client, make_project, app):
    dev = enroll_client("dev")
    make_project("vision/seg", members=["dev"])
    run = dev.http.post("/api/v1/runs", json={"project": "vision/seg", "name": "n"}).json()["id"]
    project_id, user_id = _ids(app)
    return run, project_id, user_id


def _expect_integrity_error(app, build):
    with app.state.session_factory() as session:
        session.add(build())
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_metric_series_is_unique_per_run_name_and_context(app, seeded):
    run, _, _ = seeded
    with app.state.session_factory() as session:
        session.add(MetricSeries(run_id=run, name="loss", context={"subset": "val"}))
        session.commit()
    _expect_integrity_error(
        app, lambda: MetricSeries(run_id=run, name="loss", context={"subset": "val"})
    )


def test_tag_names_are_unique_per_project(app, seeded):
    _, project, _ = seeded
    with app.state.session_factory() as session:
        session.add(Tag(id="tag_a", project_id=project, name="baseline"))
        session.commit()
    _expect_integrity_error(app, lambda: Tag(id="tag_b", project_id=project, name="baseline"))


def test_a_run_has_each_tag_once(app, seeded):
    run, project, _ = seeded
    with app.state.session_factory() as session:
        session.add(Tag(id="tag_c", project_id=project, name="fast"))
        session.commit()
    with app.state.session_factory() as session:
        session.add(RunTag(run_id=run, tag_id="tag_c"))
        session.commit()
    _expect_integrity_error(app, lambda: RunTag(run_id=run, tag_id="tag_c"))


def test_sequence_items_are_unique_per_sequence_step_and_index(app, seeded):
    run, _, _ = seeded
    with app.state.session_factory() as session:
        seq = Sequence(run_id=run, kind="image", name="samples", context={})
        session.add(seq)
        session.commit()
        seq_id = seq.id
        session.add(SequenceItem(sequence_id=seq_id, step=1, idx=0, ts=1.0, blob_key="a.png"))
        session.commit()
    _expect_integrity_error(
        app, lambda: SequenceItem(sequence_id=seq_id, step=1, idx=0, ts=2.0, blob_key="b.png")
    )


def test_sequences_are_unique_per_kind_and_name(app, seeded):
    run, _, _ = seeded
    with app.state.session_factory() as session:
        session.add(Sequence(run_id=run, kind="text", name="log", context={}))
        session.commit()
    _expect_integrity_error(app, lambda: Sequence(run_id=run, kind="text", name="log", context={}))
    with app.state.session_factory() as session:
        session.add(Sequence(run_id=run, kind="audio", name="log", context={}))
        session.commit()  # another kind may reuse the name


def test_bookmarks_belong_to_a_user_and_keep_their_state(app, seeded):
    _, _, user = seeded
    with app.state.session_factory() as session:
        session.add(
            ExplorerState(
                id="bmk_1", user_id=user, kind="runs", title="Best loss",
                state={"filter": "run.archived == False", "metric": "loss"},
            )
        )
        session.commit()
    with app.state.session_factory() as session:
        saved = session.get(ExplorerState, "bmk_1")
        assert saved.state["metric"] == "loss" and saved.created_at is not None

"""Direct tests for the shared access helpers in mlops_server.services.access."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from mlops_server.ids import new_id
from mlops_server.models import Experiment, Job, Project
from mlops_server.security.deps import Principal
from mlops_server.services import access
from sqlalchemy import select


def _client(enrolled) -> Principal:
    return Principal(enrolled.client_id, "client", enrolled.user_id, frozenset(), False)


def _seed(app, project_slug: str, owner_id: str, agent_id: str | None = None):
    """Insert an experiment (and, if agent_id is given, a job assigned to that agent)."""
    with app.state.session_factory() as session:
        project = session.scalar(select(Project).where(Project.slug == project_slug))
        exp = Experiment(
            id=new_id("exp"), project_id=project.id, owner_id=owner_id, name="exp"
        )
        session.add(exp)
        job_id = None
        if agent_id is not None:
            job = Job(
                id=new_id("job"), experiment_id=exp.id, project_id=project.id,
                created_by=owner_id, spec={}, queue="default", agent_id=agent_id,
            )
            session.add(job)
            exp.job_id = job.id
            job_id = job.id
        session.commit()
        return exp.id, job_id


def test_ensure_member_returns_404_for_non_member_and_missing_project(
    app, server, enroll_client, make_project
):
    dev, eve = enroll_client("dev"), enroll_client("eve")
    make_project("vision/seg", members=["dev"])
    with app.state.session_factory() as session:
        with pytest.raises(HTTPException) as non_member:
            access.ensure_member(session, _client(eve), "vision/seg")
        assert non_member.value.status_code == 404

        with pytest.raises(HTTPException) as missing:
            access.ensure_member(session, _client(dev), "nope/x")
        assert missing.value.status_code == 404

        assert access.ensure_member(session, _client(dev), "vision/seg").slug == "vision/seg"


def test_run_principal_reads_only_its_own_experiment(
    app, server, enroll_client, make_project, make_agent
):
    dev = enroll_client("dev")
    make_project("vision/seg", members=["dev"])
    agent = make_agent()
    own_exp, own_job = _seed(app, "vision/seg", dev.user_id, agent.agent_id)
    other_exp, _ = _seed(app, "vision/seg", dev.user_id, agent.agent_id)
    run = Principal(own_job, "run", dev.user_id, frozenset(), False, own_exp, own_job)
    with app.state.session_factory() as session:
        assert access.load_experiment(session, run, own_exp, write=False).id == own_exp
        with pytest.raises(HTTPException) as denied:
            access.load_experiment(session, run, other_exp, write=False)
        assert denied.value.status_code == 404


def test_agent_principal_reads_only_experiments_of_its_jobs(
    app, server, enroll_client, make_project, make_agent
):
    dev = enroll_client("dev")
    make_project("vision/seg", members=["dev"])
    agent, other_agent = make_agent(), make_agent()
    assigned_exp, _ = _seed(app, "vision/seg", dev.user_id, agent.agent_id)
    foreign_exp, _ = _seed(app, "vision/seg", dev.user_id, other_agent.agent_id)
    unassigned_exp, _ = _seed(app, "vision/seg", dev.user_id)
    principal = Principal(agent.agent_id, "agent", None, frozenset(), False)
    with app.state.session_factory() as session:
        loaded = access.load_experiment(session, principal, assigned_exp, write=False)
        assert loaded.id == assigned_exp
        for hidden in (foreign_exp, unassigned_exp):
            with pytest.raises(HTTPException) as denied:
                access.load_experiment(session, principal, hidden, write=False)
            assert denied.value.status_code == 404


def test_non_owner_member_can_read_but_not_write(app, server, enroll_client, make_project):
    dev, peer = enroll_client("dev"), enroll_client("peer")
    make_project("vision/seg", members=["dev", "peer"])
    exp_id, _ = _seed(app, "vision/seg", dev.user_id)
    peer_principal = _client(peer)
    with app.state.session_factory() as session:
        assert access.load_experiment(session, peer_principal, exp_id, write=False).id == exp_id
        with pytest.raises(HTTPException) as denied:
            access.load_experiment(session, peer_principal, exp_id, write=True)
        assert denied.value.status_code == 404

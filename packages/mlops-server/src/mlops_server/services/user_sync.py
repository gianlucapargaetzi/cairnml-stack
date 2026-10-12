"""Keeps the user table in step with the IdP and revokes access of disabled users."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from mlops_server.models import Client, Experiment, Job, User, WebSession
from mlops_server.services.audit import record
from mlops_server.services.directory import Directory, DirectoryError

log = logging.getLogger(__name__)

TERMINAL = ("finished", "failed", "cancelled")


@dataclass
class SyncReport:
    checked: int = 0
    disabled: list[str] = field(default_factory=list)
    reenabled: list[str] = field(default_factory=list)
    roles_changed: list[str] = field(default_factory=list)
    errors: int = 0

    def as_dict(self) -> dict:
        return {"checked": self.checked, "disabled": self.disabled, "reenabled": self.reenabled,
                "roles_changed": self.roles_changed, "errors": self.errors}


def _delete_sessions(session: Session, user_id: str) -> int:
    return session.query(WebSession).filter(WebSession.user_id == user_id).delete()


def disable_user(session: Session, user: User, now: datetime) -> dict:
    user.disabled = True
    clients = session.scalars(
        select(Client).where(Client.user_id == user.id, Client.revoked_at.is_(None))
    ).all()
    for client in clients:
        client.revoked_at = now
    sessions = _delete_sessions(session, user.id)
    cancelled = stopping = 0
    # Row locks in the same order as set_status and the reaper: job first, then experiment.
    jobs = session.scalars(
        select(Job)
        .where(Job.created_by == user.id, Job.status.in_(("queued", "assigned", "running")))
        .order_by(Job.id)  # every pass locks in the same order, so two passes cannot deadlock
        .with_for_update(of=Job)
    ).all()
    for job in jobs:
        if job.status == "queued":
            job.status, job.finished_at, job.message = "cancelled", now, "owner was disabled"
            experiment = session.get(
                Experiment, job.experiment_id, with_for_update=True, populate_existing=True
            )
            if experiment.status not in TERMINAL:
                experiment.status, experiment.finished_at = "cancelled", now
            cancelled += 1
        else:
            job.cancel_requested = True
            stopping += 1
    detail = {"clients_revoked": len(clients), "sessions_deleted": sessions,
              "jobs_cancelled": cancelled, "jobs_stopping": stopping}
    record(session, "user-sync", "user.disabled", None, user=user.id, **detail)
    return detail


_ANSWER_FAILED = object()


def sync_users(session: Session, directory: Directory, now: datetime | None = None) -> SyncReport:
    now = now or datetime.now(UTC)
    report = SyncReport()
    users = session.scalars(select(User).order_by(User.created_at)).all()
    # Ask the IdP about every user before any row is locked: no lock is held across IdP calls.
    answers = []
    for user in users:
        report.checked += 1
        try:
            answers.append((user, directory.get_user(user.idp_subject)))
        except DirectoryError:
            report.errors += 1
            answers.append((user, _ANSWER_FAILED))
    # If every user comes back gone or disabled, the directory is more likely wrong (a bad URL,
    # a gateway 404) than the whole company was offboarded: disable nobody in this pass.
    mass_anomaly = report.checked > 1 and all(
        answer is None or (answer is not _ANSWER_FAILED and not answer.enabled)
        for _, answer in answers
    )
    held = 0
    for user, answer in answers:
        if answer is _ANSWER_FAILED:
            continue  # counted above; changes nothing for this user
        if answer is None or not answer.enabled:
            if not user.disabled:
                if mass_anomaly:
                    report.errors += 1
                    held += 1
                    continue
                disable_user(session, user, now)
                report.disabled.append(user.id)
        else:
            if user.disabled:
                # Only the flag comes back: revoked client keys stay revoked; enrol again instead.
                user.disabled = False
                report.reenabled.append(user.id)
                record(session, "user-sync", "user.reenabled", None, user=user.id)
            if sorted(user.roles or []) != list(answer.roles):
                user.roles = list(answer.roles)
                report.roles_changed.append(user.id)
                record(session, "user-sync", "user.roles_changed", None, user=user.id,
                       roles=list(answer.roles))
        session.commit()  # per user, so job locks are never held for long
    if held:
        log.warning("user sync refused to disable %d users: the directory reported all users "
                    "as gone or disabled", held)
    return report


class UserSyncThread:
    def __init__(self, session_factory, directory: Directory, interval_s: int) -> None:
        self._factory = session_factory
        self._directory = directory
        self._interval = interval_s
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="user-sync", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                with self._factory() as session:
                    report = sync_users(session, self._directory)
                    session.commit()
                if report.disabled or report.errors:
                    log.warning("user sync: %s", report.as_dict())
            except Exception:  # keep the loop alive
                log.exception("user sync iteration failed")

"""Keeps the user table in step with the IdP and revokes access of disabled users."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from mlops_server.models import Client, Experiment, Job, User
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
    try:
        from mlops_server.models import WebSession  # added in Task 44
    except ImportError:
        return 0
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


def sync_users(session: Session, directory: Directory, now: datetime | None = None) -> SyncReport:
    now = now or datetime.now(UTC)
    report = SyncReport()
    for user in session.scalars(select(User).order_by(User.created_at)).all():
        report.checked += 1
        try:
            info = directory.get_user(user.idp_subject)
        except DirectoryError:
            report.errors += 1
            continue
        if info is None or not info.enabled:
            if not user.disabled:
                disable_user(session, user, now)
                report.disabled.append(user.id)
            continue
        if user.disabled:
            # Only the flag comes back: revoked client keys stay revoked; enrolling again is needed.
            user.disabled = False
            report.reenabled.append(user.id)
            record(session, "user-sync", "user.reenabled", None, user=user.id)
        if sorted(user.roles or []) != list(info.roles):
            user.roles = list(info.roles)
            report.roles_changed.append(user.id)
            record(session, "user-sync", "user.roles_changed", None, user=user.id,
                   roles=list(info.roles))
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

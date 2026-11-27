"""All SQL for releases. Every method opens its own session and commits before it returns; the
SQLite engine starts each transaction with BEGIN IMMEDIATE, so read-then-write is serialised."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from app.models import ArtifactRef, Decision, Release, ReleaseRequest, ReleaseStatus
from app.repos.tables import ReleaseRow


def _to_release(row: ReleaseRow) -> Release:
    status: ReleaseStatus = row.status  # type: ignore[assignment]
    return Release(
        release_id=UUID(row.release_id),
        artifact=ArtifactRef(name=row.artifact_name, version=row.artifact_version),
        status=status,
        requested_by=row.requested_by,
        requested_at=row.requested_at,
        decided_by=row.decided_by,
        decided_at=row.decided_at,
        promoted_at=row.promoted_at,
    )


@dataclass(frozen=True)
class Outcome:
    """Result of a state change: `not_found`, `conflict` (rule violated; `release` is the current
    state) or `ok`."""

    kind: Literal["ok", "not_found", "conflict"]
    release: Release | None = None


class ReleaseRepo:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def create(self, release_id: UUID, request: ReleaseRequest, now: str) -> Release:
        with self._factory() as session:
            row = ReleaseRow(
                release_id=str(release_id),
                artifact_name=request.artifact.name,
                artifact_version=request.artifact.version,
                status="pending",
                requested_by=request.requested_by,
                requested_at=now,
            )
            session.add(row)
            session.commit()
            return _to_release(row)

    def get(self, release_id: UUID) -> Release | None:
        with self._factory() as session:
            row = session.get(ReleaseRow, str(release_id))
            return _to_release(row) if row else None

    def decide(self, release_id: UUID, decision: Decision, decided_by: str, now: str) -> Outcome:
        """Record the one, final decision; `conflict` when the release already has one."""
        with self._factory() as session:
            row = session.get(ReleaseRow, str(release_id))
            if row is None:
                return Outcome("not_found")
            if row.status != "pending":
                return Outcome("conflict", _to_release(row))
            row.status = decision
            row.decided_by = decided_by
            row.decided_at = now
            session.commit()
            return Outcome("ok", _to_release(row))

    def promote(self, release_id: UUID, now: str) -> Outcome:
        """Set promoted_at on an approved release; a second promote keeps the first time (Q-31)."""
        with self._factory() as session:
            row = session.get(ReleaseRow, str(release_id))
            if row is None:
                return Outcome("not_found")
            if row.status != "approved":
                return Outcome("conflict", _to_release(row))
            if row.promoted_at is None:
                row.promoted_at = now
                session.commit()
            return Outcome("ok", _to_release(row))

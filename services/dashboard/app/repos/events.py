"""Event intake: store the event once and fold it into the view tables."""

import threading
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    ArtifactUploaded,
    BuildFinished,
    BuildStarted,
    Event,
    ReleaseDecided,
    ReleaseRequested,
    parse_timestamp,
)
from app.repos.tables import ArtifactRow, BuildRow, EventRow, ReleaseRow

# One writer at a time: the fold below is read-modify-write on view rows.
_write_lock = threading.Lock()


def _later(current: datetime | None, new: datetime) -> datetime:
    return new if current is None or new > current else current


def _build(session: Session, event: BuildStarted | BuildFinished, ts: datetime) -> None:
    data = event.data
    row = session.get(BuildRow, data.build_id)
    if row is None:
        row = BuildRow(
            build_id=data.build_id,
            pipeline_name=data.pipeline_name,
            started_at=None,
            finished_at=None,
            outcome=None,
            failed_step=None,
            failure_reason=None,
            steps=[],
            last_event_at=ts,
        )
        session.add(row)
    row.last_event_at = _later(row.last_event_at, ts)
    if isinstance(event, BuildStarted):
        if row.started_at is None:
            row.started_at = event.occurred_at
    elif row.finished_at is None:
        fin = event.data
        row.finished_at = event.occurred_at
        row.outcome = fin.outcome
        row.failed_step = fin.failed_step
        row.failure_reason = fin.failure_reason
        row.steps = [step.model_dump() for step in fin.steps]


def _artifact(session: Session, event: ArtifactUploaded) -> None:
    data = event.data
    if session.get(ArtifactRow, (data.name, data.version)) is None:
        session.add(
            ArtifactRow(
                name=data.name,
                version=data.version,
                checksum=data.checksum,
                size_bytes=data.size_bytes,
                build_id=data.build_id,
                uploaded_at=data.uploaded_at,
                uploaded_ts=parse_timestamp(data.uploaded_at),
            )
        )


def _release(session: Session, event: ReleaseRequested | ReleaseDecided, ts: datetime) -> None:
    data = event.data
    row = session.get(ReleaseRow, data.release_id)
    if row is None:
        row = ReleaseRow(
            release_id=data.release_id,
            artifact_name=data.artifact.name,
            artifact_version=data.artifact.version,
            requested_by=None,
            requested_at=None,
            decision=None,
            decided_by=None,
            decided_at=None,
            last_event_at=ts,
        )
        session.add(row)
    row.last_event_at = _later(row.last_event_at, ts)
    if isinstance(event, ReleaseRequested):
        if row.requested_at is None:
            row.requested_by = event.data.requested_by
            row.requested_at = event.data.requested_at
    elif row.decided_at is None:
        row.decision = event.data.decision
        row.decided_by = event.data.decided_by
        row.decided_at = event.data.decided_at


def ingest(session: Session, event: Event) -> bool:
    """Store one event; return False (changing nothing) when its event_id was accepted before.

    Commits before returning, so the caller can answer 202 and the next read sees the event.
    """
    ts = parse_timestamp(event.occurred_at)
    with _write_lock:
        try:
            if session.scalar(select(EventRow.event_id).where(EventRow.event_id == event.event_id)):
                return False
            session.add(
                EventRow(
                    event_id=event.event_id,
                    type=event.type,
                    occurred_at=ts,
                    body=event.model_dump(mode="json"),
                )
            )
            session.flush()
            if isinstance(event, BuildStarted | BuildFinished):
                _build(session, event, ts)
            elif isinstance(event, ArtifactUploaded):
                _artifact(session, event)
            else:
                _release(session, event, ts)
            session.commit()
        except IntegrityError:
            session.rollback()
            return False
        except Exception:
            session.rollback()
            raise
    return True

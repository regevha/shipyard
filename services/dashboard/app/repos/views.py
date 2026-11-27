"""Read side: the three views, newest first by the latest event's occurred_at."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Artifact,
    ArtifactPage,
    ArtifactRef,
    BuildPage,
    BuildStatus,
    BuildView,
    FailureReason,
    ReleasePage,
    ReleaseStatus,
    ReleaseView,
    StepResult,
)
from app.repos.tables import ArtifactRow, BuildRow, ReleaseRow

_MAX_OFFSET = 2**62  # below SQLite's int64 limit; any larger offset is past the end anyway


def list_builds(session: Session, limit: int, offset: int, status: BuildStatus | None) -> BuildPage:
    query = select(BuildRow)
    if status == "running":
        query = query.where(BuildRow.outcome.is_(None))
    elif status is not None:
        query = query.where(BuildRow.outcome == status)
    query = query.order_by(BuildRow.last_event_at.desc(), BuildRow.build_id).limit(limit)
    rows = session.scalars(query.offset(min(offset, _MAX_OFFSET))).all()
    items = [
        BuildView(
            build_id=r.build_id,
            pipeline_name=r.pipeline_name,
            status="running" if r.outcome is None else _outcome(r.outcome),
            started_at=r.started_at,
            finished_at=r.finished_at,
            failed_step=r.failed_step,
            failure_reason=_reason(r.failure_reason),
            steps=[StepResult(**step) for step in r.steps],
        )
        for r in rows
    ]
    return BuildPage(items=items, limit=limit, offset=offset)


def _outcome(value: str) -> BuildStatus:
    return "passed" if value == "passed" else "failed"


def _reason(value: str | None) -> FailureReason | None:
    if value is None:
        return None
    return "internal error" if value == "internal error" else "artifact upload failed"


def list_artifacts(session: Session, limit: int, offset: int) -> ArtifactPage:
    rows = session.scalars(
        select(ArtifactRow)
        .order_by(ArtifactRow.uploaded_ts.desc(), ArtifactRow.name, ArtifactRow.version)
        .limit(limit)
        .offset(min(offset, _MAX_OFFSET))
    ).all()
    items = [
        Artifact(
            name=r.name,
            version=r.version,
            checksum=r.checksum,
            size_bytes=r.size_bytes,
            build_id=r.build_id,
            uploaded_at=r.uploaded_at,
        )
        for r in rows
    ]
    return ArtifactPage(items=items, limit=limit, offset=offset)


def _release_status(decision: str | None) -> ReleaseStatus:
    if decision is None:
        return "pending"
    return "approved" if decision == "approved" else "rejected"


def list_releases(session: Session, limit: int, offset: int) -> ReleasePage:
    rows = session.scalars(
        select(ReleaseRow)
        .order_by(ReleaseRow.last_event_at.desc(), ReleaseRow.release_id)
        .limit(limit)
        .offset(min(offset, _MAX_OFFSET))
    ).all()
    items = [
        ReleaseView(
            release_id=r.release_id,
            artifact=ArtifactRef(name=r.artifact_name, version=r.artifact_version),
            status=_release_status(r.decision),
            requested_by=r.requested_by,
            requested_at=r.requested_at,
            decided_by=r.decided_by,
            decided_at=r.decided_at,
        )
        for r in rows
    ]
    return ReleasePage(items=items, limit=limit, offset=offset)

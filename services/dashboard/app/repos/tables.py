"""SQLAlchemy tables (see services/dashboard/DATA_MODEL.md)."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Index, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class EventRow(Base):
    """Every accepted event, once per event_id (first accepted body wins)."""

    __tablename__ = "events"

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    type: Mapped[str] = mapped_column(String(32))
    occurred_at: Mapped[datetime] = mapped_column(DateTime)
    body: Mapped[dict[str, Any]] = mapped_column(JSON)


class BuildRow(Base):
    __tablename__ = "builds"
    __table_args__ = (Index("ix_builds_last_event_at", "last_event_at"),)

    build_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    pipeline_name: Mapped[str] = mapped_column(String(100))
    started_at: Mapped[str | None] = mapped_column(String(40))
    finished_at: Mapped[str | None] = mapped_column(String(40))
    outcome: Mapped[str | None] = mapped_column(String(10), index=True)
    failed_step: Mapped[str | None] = mapped_column(String)
    failure_reason: Mapped[str | None] = mapped_column(String)
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    last_event_at: Mapped[datetime] = mapped_column(DateTime)


class ArtifactRow(Base):
    __tablename__ = "artifacts"
    __table_args__ = (Index("ix_artifacts_uploaded_ts", "uploaded_ts"),)

    name: Mapped[str] = mapped_column(String(100), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    checksum: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    build_id: Mapped[str] = mapped_column(String(36))
    uploaded_at: Mapped[str] = mapped_column(String(40))
    uploaded_ts: Mapped[datetime] = mapped_column(DateTime)


class ReleaseRow(Base):
    __tablename__ = "releases"
    __table_args__ = (Index("ix_releases_last_event_at", "last_event_at"),)

    release_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    artifact_name: Mapped[str] = mapped_column(String(100))
    artifact_version: Mapped[int] = mapped_column(Integer)
    requested_by: Mapped[str | None] = mapped_column(String)
    requested_at: Mapped[str | None] = mapped_column(String(40))
    decision: Mapped[str | None] = mapped_column(String(10))
    decided_by: Mapped[str | None] = mapped_column(String)
    decided_at: Mapped[str | None] = mapped_column(String(40))
    last_event_at: Mapped[datetime] = mapped_column(DateTime)

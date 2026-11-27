"""SQLAlchemy tables (documented in DATA_MODEL.md)."""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ReleaseRow(Base):
    __tablename__ = "releases"

    release_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    artifact_name: Mapped[str] = mapped_column(String(100))
    # Text, not INTEGER: the contract sets no upper bound on a version; SQLite stops at 2^63-1.
    artifact_version: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String(16))
    requested_by: Mapped[str] = mapped_column(String)
    requested_at: Mapped[str] = mapped_column(String(30))
    decided_by: Mapped[str | None] = mapped_column(String, nullable=True)
    decided_at: Mapped[str | None] = mapped_column(String(30), nullable=True)
    promoted_at: Mapped[str | None] = mapped_column(String(30), nullable=True)

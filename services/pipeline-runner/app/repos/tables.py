"""SQLAlchemy tables (documented in DATA_MODEL.md)."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class RunRow(Base):
    __tablename__ = "runs"

    build_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    pipeline_name: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[str] = mapped_column(String(30))
    finished_at: Mapped[str | None] = mapped_column(String(30), nullable=True)
    failed_step: Mapped[str | None] = mapped_column(String, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)


class StepRow(Base):
    __tablename__ = "run_steps"

    build_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("runs.build_id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    command: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String(16))
    started_at: Mapped[str | None] = mapped_column(String(30), nullable=True)
    finished_at: Mapped[str | None] = mapped_column(String(30), nullable=True)

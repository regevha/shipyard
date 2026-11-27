"""Artifact metadata table and the create/find functions (all SQL lives here)."""

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import IO

from sqlalchemy import DateTime, Engine, Integer, String, UniqueConstraint, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from app.models import MAX_VERSION, Artifact
from app.repos.blobs import BlobStore

MAX_VERSION_RETRIES = 10


class Base(DeclarativeBase):
    pass


class ArtifactRow(Base):
    __tablename__ = "artifacts"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_artifacts_name_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    build_id: Mapped[str] = mapped_column(String(36), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    blob_path: Mapped[str] = mapped_column(String(255), nullable=False)


def _to_model(row: ArtifactRow) -> Artifact:
    return Artifact(
        name=row.name,
        version=row.version,
        checksum=row.checksum,
        size_bytes=row.size_bytes,
        build_id=row.build_id,
        uploaded_at=row.uploaded_at.replace(tzinfo=UTC),
    )


class ArtifactRepo:
    def __init__(self, engine: Engine, blobs: BlobStore) -> None:
        self._engine = engine
        self._blobs = blobs

    def create_tables(self) -> None:
        Base.metadata.create_all(self._engine)
        self._blobs.ensure()

    def create(
        self, name: str, build_id: str, checksum: str, size_bytes: int, source: IO[bytes]
    ) -> Artifact:
        """Write the blob, then commit the row with the next version; returns after the commit."""
        rel = self._blobs.write(source)
        uploaded_at = datetime.now(UTC).replace(microsecond=0, tzinfo=None)
        try:
            for _ in range(MAX_VERSION_RETRIES):
                with Session(self._engine) as session:
                    current = session.scalar(
                        select(func.max(ArtifactRow.version)).where(ArtifactRow.name == name)
                    )
                    if (current or 0) >= MAX_VERSION:
                        raise RuntimeError("version cap reached")  # nothing stored; 500
                    row = ArtifactRow(
                        id=str(uuid.uuid4()),
                        name=name,
                        version=(current or 0) + 1,
                        checksum=checksum,
                        size_bytes=size_bytes,
                        build_id=build_id,
                        uploaded_at=uploaded_at,
                        blob_path=rel,
                    )
                    session.add(row)
                    try:
                        session.commit()
                    except IntegrityError:
                        session.rollback()
                        continue  # another upload took this version; try the next
                    return _to_model(row)
            raise RuntimeError("could not assign a version")
        except BaseException:
            self._blobs.delete(rel)
            raise

    def find(self, name: str, version: int) -> tuple[Artifact, Path] | None:
        with Session(self._engine) as session:
            row = session.scalar(
                select(ArtifactRow).where(ArtifactRow.name == name, ArtifactRow.version == version)
            )
            if row is None:
                return None
            return _to_model(row), self._blobs.path(row.blob_path)

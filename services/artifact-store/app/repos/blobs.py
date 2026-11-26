"""Blob files under $SHIPYARD_DATA_DIR/artifact_store_blobs/ (the database holds metadata)."""

import os
import shutil
import uuid
from pathlib import Path
from typing import IO


class BlobStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def ensure(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def write(self, source: IO[bytes]) -> str:
        """Copy source to a new file; returns the path relative to the root."""
        self.ensure()
        rel = uuid.uuid4().hex
        final = self.root / rel
        tmp = self.root / f".{rel}.part"
        try:
            source.seek(0)
            with tmp.open("wb") as out:
                shutil.copyfileobj(source, out, 1024 * 1024)
                out.flush()
                os.fsync(out.fileno())
            tmp.replace(final)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        return rel

    def path(self, rel: str) -> Path:
        return self.root / rel

    def delete(self, rel: str) -> None:
        self.path(rel).unlink(missing_ok=True)

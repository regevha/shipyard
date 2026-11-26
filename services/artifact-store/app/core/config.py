"""Settings read from environment variables (see environment.md, Wave 2 setup)."""

import os
from dataclasses import dataclass
from pathlib import Path

MAX_UPLOAD_BYTES = 104_857_600  # 100 MiB (Q-18 default)
SERVICE_INDEX = 1  # artifact-store in the port formula
DASHBOARD_INDEX = 3


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    database_url: str
    dashboard_url: str

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Settings":
        e = dict(os.environ) if env is None else env
        slot = int(e.get("SHIPYARD_SLOT", "0"))
        data_dir = Path(e.get("SHIPYARD_DATA_DIR") or f"/tmp/shipyard/slot{slot}")
        database_url = e.get("ARTIFACT_STORE_DATABASE_URL") or (
            f"sqlite:///{data_dir}/artifact_store.db"
        )
        dashboard_url = e.get("DASHBOARD_URL") or f"http://127.0.0.1:{18000 + 10 * slot + 3}"
        return cls(data_dir=data_dir, database_url=database_url, dashboard_url=dashboard_url)

    @property
    def blob_dir(self) -> Path:
        return self.data_dir / "artifact_store_blobs"

"""Settings read from environment variables (docs/team/environment.md, Wave 2 setup)."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _slot() -> int:
    return int(os.environ.get("SHIPYARD_SLOT", "0"))


def _data_dir() -> str:
    return os.environ.get("SHIPYARD_DATA_DIR", f"/tmp/shipyard/slot{_slot()}")


@dataclass(frozen=True)
class Settings:
    database_url: str
    dashboard_url: str
    # Event sender (PLAN.md Conventions): 3 attempts, 2 s timeout, waits 0.5 s then 1 s.
    event_timeout_seconds: float = 2.0
    event_backoff_seconds: tuple[float, ...] = (0.5, 1.0)

    @classmethod
    def from_env(cls) -> Settings:
        base = 18000 + 10 * _slot()
        env = os.environ
        return cls(
            database_url=env.get(
                "RELEASE_SERVICE_DATABASE_URL", f"sqlite:///{_data_dir()}/release_service.db"
            ),
            dashboard_url=env.get("DASHBOARD_URL", f"http://127.0.0.1:{base + 3}"),
        )

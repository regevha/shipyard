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
    artifact_store_url: str
    dashboard_url: str
    # #132: the fake upload is a few bytes to a local store, so a healthy answer takes milliseconds.
    # 10 s is far above that, yet bounds how long a dead store keeps a build in "running".
    upload_timeout_seconds: float = 10.0
    # Simulated duration of each step, so a running build is visible in the demo.
    step_seconds: float = 0.5

    @classmethod
    def from_env(cls) -> Settings:
        base = 18000 + 10 * _slot()
        env = os.environ
        return cls(
            database_url=env.get(
                "PIPELINE_RUNNER_DATABASE_URL", f"sqlite:///{_data_dir()}/pipeline_runner.db"
            ),
            artifact_store_url=env.get("ARTIFACT_STORE_URL", f"http://127.0.0.1:{base + 1}"),
            dashboard_url=env.get("DASHBOARD_URL", f"http://127.0.0.1:{base + 3}"),
            upload_timeout_seconds=float(env.get("PIPELINE_RUNNER_UPLOAD_TIMEOUT_SECONDS", "10")),
            step_seconds=float(env.get("PIPELINE_RUNNER_STEP_SECONDS", "0.5")),
        )

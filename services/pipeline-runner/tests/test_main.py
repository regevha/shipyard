from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import app, create_app


def test_openapi_title_is_service_name() -> None:
    response = TestClient(app).get("/openapi.json")
    assert response.status_code == 200
    assert response.json()["info"]["title"] == "pipeline-runner"


def test_settings_default_from_slot(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "PIPELINE_RUNNER_DATABASE_URL",
        "ARTIFACT_STORE_URL",
        "DASHBOARD_URL",
        "PIPELINE_RUNNER_UPLOAD_TIMEOUT_SECONDS",
        "PIPELINE_RUNNER_STEP_SECONDS",
        "SHIPYARD_DATA_DIR",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SHIPYARD_SLOT", "2")
    s = Settings.from_env()
    assert s.database_url == "sqlite:////tmp/shipyard/slot2/pipeline_runner.db"
    assert s.artifact_store_url == "http://127.0.0.1:18021"
    assert s.dashboard_url == "http://127.0.0.1:18023"
    assert s.upload_timeout_seconds == 10.0
    assert s.step_seconds == 0.5


def test_settings_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PIPELINE_RUNNER_UPLOAD_TIMEOUT_SECONDS", "3")
    monkeypatch.setenv("PIPELINE_RUNNER_STEP_SECONDS", "0")
    monkeypatch.setenv("ARTIFACT_STORE_URL", "http://a.test")
    s = Settings.from_env()
    assert (s.upload_timeout_seconds, s.step_seconds, s.artifact_store_url) == (
        3.0,
        0.0,
        "http://a.test",
    )


def test_startup_creates_tables_in_a_file_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "sub" / "runner.db"
    monkeypatch.setenv("PIPELINE_RUNNER_DATABASE_URL", f"sqlite:///{db}")
    # #167 review note: never post to a real $DASHBOARD_URL; nothing listens on this closed port
    monkeypatch.setenv("DASHBOARD_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("ARTIFACT_STORE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("PIPELINE_RUNNER_STEP_SECONDS", "0")
    with TestClient(create_app()) as c:
        body = {"name": "p", "steps": [{"name": "a", "command": "fail"}]}
        build_id = c.post("/runs", json=body).json()["build_id"]
        assert c.get(f"/runs/{build_id}").status_code == 200
    assert db.exists()

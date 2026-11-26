from fastapi.testclient import TestClient

from app.main import app


def test_openapi_title_is_service_name() -> None:
    response = TestClient(app).get("/openapi.json")
    assert response.status_code == 200
    assert response.json()["info"]["title"] == "artifact-store"


def test_settings_defaults_follow_slot() -> None:
    from app.core.config import Settings

    s = Settings.from_env({"SHIPYARD_SLOT": "3"})
    assert str(s.data_dir) == "/tmp/shipyard/slot3"
    assert s.database_url == "sqlite:////tmp/shipyard/slot3/artifact_store.db"
    assert s.dashboard_url == "http://127.0.0.1:18033"
    assert s.blob_dir.name == "artifact_store_blobs"
    explicit = Settings.from_env(
        {
            "SHIPYARD_DATA_DIR": "/x",
            "ARTIFACT_STORE_DATABASE_URL": "sqlite://",
            "DASHBOARD_URL": "http://d",
        }
    )
    assert (str(explicit.data_dir), explicit.database_url, explicit.dashboard_url) == (
        "/x",
        "sqlite://",
        "http://d",
    )


def test_file_database_and_blobs_survive_restart(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from app.core.config import Settings
    from app.main import create_app

    s = Settings(tmp_path, f"sqlite:///{tmp_path}/a.db", "http://127.0.0.1:1")
    build = "5d0c6f1e-2b7a-4c39-9e8d-41a2f6b3c701"
    with TestClient(create_app(s)) as c:
        assert c.post(f"/artifacts/app?build_id={build}", content=b"hi").status_code == 201
    with TestClient(create_app(s)) as c:
        assert c.get("/artifacts/app/versions/1").content == b"hi"

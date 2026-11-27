"""Q-40 (#170): versions are capped at 2^63-1 (events.yml ArtifactVersion)."""

from datetime import datetime
from io import BytesIO

from conftest import BUILD, Dashboard
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.events import EventSender
from app.models import MAX_VERSION
from app.repos.artifacts import ArtifactRepo, ArtifactRow


def seed_max(client: TestClient, name: str = "app") -> None:
    """Put a row at version 2^63-1 (with its blob), so the next version would pass the cap."""
    repo: ArtifactRepo = client.app.state.repo  # type: ignore[attr-defined]
    blob = repo._blobs.write(BytesIO(b"top"))
    with Session(repo._engine) as session:
        session.add(
            ArtifactRow(
                id="00000000-0000-4000-8000-000000000001",
                name=name,
                version=MAX_VERSION,
                checksum="0" * 64,
                size_bytes=3,
                build_id=BUILD,
                uploaded_at=datetime(2026, 1, 1),
                blob_path=blob,
            )
        )
        session.commit()


def blob_files(client: TestClient) -> list[str]:
    repo: ArtifactRepo = client.app.state.repo  # type: ignore[attr-defined]
    return sorted(p.name for p in repo._blobs.path("").iterdir())


def test_q40_download_version_max_is_404_when_not_stored(client: TestClient) -> None:
    r = client.get(f"/artifacts/app/versions/{MAX_VERSION}")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_q40_download_version_above_max_is_422(client: TestClient) -> None:
    for version in (MAX_VERSION + 1, 99999999999999999999999):
        r = client.get(f"/artifacts/app/versions/{version}")
        assert r.status_code == 422
        error = r.json()["error"]
        assert error["code"] == "validation_failed"
        assert error["details"][0]["location"] == "path.version"
    # 422 comes before 404: the name is unknown too
    assert client.get(f"/artifacts/unknown/versions/{MAX_VERSION + 1}").status_code == 422


def test_q40_store_never_assigns_above_max(
    client: TestClient, dashboard: Dashboard, sender: EventSender
) -> None:
    seed_max(client)
    before = blob_files(client)
    quiet = TestClient(client.app, raise_server_exceptions=False)
    r = quiet.post(f"/artifacts/app?build_id={BUILD}", content=b"more")
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "internal_error"
    assert blob_files(client) == before  # no blob file left behind
    assert sender.wait_idle() and dashboard.calls == 0  # no event
    assert client.get(f"/artifacts/app/versions/{MAX_VERSION}").content == b"top"  # no new row
    # another name is unaffected
    assert client.post(f"/artifacts/other?build_id={BUILD}", content=b"x").status_code == 201

import json

import httpx
from conftest import BUILD, Dashboard
from fastapi.testclient import TestClient
from openapi_conformance import find_contract, schema_validator

from app.core.config import Settings
from app.core.events import EventSender
from app.main import create_app
from app.repos.artifacts import ArtifactRepo

EVENT = schema_validator(
    find_contract("api-artifact-store.yml"), "events.yml#/$defs/ArtifactUploaded"
)


def up(client: TestClient, name: str = "app", data: bytes = b"hello") -> httpx.Response:
    """Upload, then wait until the sender has nothing pending (no sleeping)."""
    response: httpx.Response = client.post(f"/artifacts/{name}?build_id={BUILD}", content=data)
    sender: EventSender = client.app.state.sender  # type: ignore[attr-defined]
    assert sender.wait_idle()
    return response


def test_artifact_uploaded_event_sent_after_commit(
    client: TestClient, dashboard: Dashboard
) -> None:
    seen_in_db: list[int] = []
    repo: ArtifactRepo = client.app.state.repo  # type: ignore[attr-defined]

    def hook(request: httpx.Request) -> None:
        # at the moment the event is sent (on the loop thread), the row and the blob are committed
        found = repo.find("app", 1)
        seen_in_db.append(200 if found is not None and found[1].is_file() else 404)

    dashboard.hook = hook
    r = up(client)
    assert r.status_code == 201
    assert seen_in_db == [200]
    (event,) = dashboard.events
    EVENT.validate(event)
    assert event["type"] == "artifact.uploaded" and event["source"] == "artifact-store"
    assert event["schema_version"] == 1
    assert event["data"] == r.json()
    assert event["occurred_at"] == r.json()["uploaded_at"]


def test_no_event_when_upload_rejected(client: TestClient, dashboard: Dashboard) -> None:
    client.post("/artifacts/-bad?build_id=" + BUILD, content=b"x")
    client.post("/artifacts/app", content=b"x")
    client.post(
        f"/artifacts/app?build_id={BUILD}", content=b"x", headers={"X-Checksum-SHA256": "0" * 64}
    )
    client.post(f"/artifacts/app?build_id={BUILD}", content=b"x" * (104_857_600 + 1))
    sender: EventSender = client.app.state.sender  # type: ignore[attr-defined]
    assert sender.wait_idle()
    assert dashboard.calls == 0


def test_event_delivery_failure_does_not_change_upload(
    client: TestClient, dashboard: Dashboard, sleeps: list[float]
) -> None:
    dashboard.error = httpx.ConnectError("down")
    r = up(client)
    assert r.status_code == 201
    assert dashboard.calls == 3 and sleeps == [0.5, 1.0]
    assert client.get("/artifacts/app/versions/1").content == b"hello"
    assert up(client).json()["version"] == 2


def test_event_retries_5xx_with_same_event_id_then_succeeds(
    client: TestClient, dashboard: Dashboard, sleeps: list[float]
) -> None:
    dashboard.statuses = [503, 500, 202]
    up(client)
    assert dashboard.calls == 3 and sleeps == [0.5, 1.0]
    assert len({e["event_id"] for e in dashboard.events}) == 1


def test_event_not_retried_on_4xx(
    client: TestClient, dashboard: Dashboard, sleeps: list[float]
) -> None:
    dashboard.statuses = [422]
    assert up(client).status_code == 201
    assert dashboard.calls == 1 and sleeps == []


def test_event_timeout_is_retried(client: TestClient, dashboard: Dashboard) -> None:
    dashboard.error = httpx.ReadTimeout("slow")
    assert up(client).status_code == 201
    assert dashboard.calls == 3


def test_sender_never_raises(settings: Settings) -> None:
    def boom(_: httpx.Request) -> httpx.Response:
        raise ValueError("unexpected")

    failing = EventSender("http://x", transport=httpx.MockTransport(boom))
    with TestClient(create_app(settings, failing)) as c:
        assert up(c).status_code == 201


def test_event_body_is_json_with_uuid_event_id(client: TestClient, dashboard: Dashboard) -> None:
    up(client)
    assert json.dumps(dashboard.events[0])
    EVENT.validate(dashboard.events[0])

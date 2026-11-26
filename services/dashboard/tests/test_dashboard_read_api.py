from collections.abc import Callable
from typing import Any

from conftest import (
    Body,
    artifact_uploaded,
    build_finished,
    build_started,
    new_id,
    release_decided,
    release_requested,
)
from fastapi.testclient import TestClient
from openapi_conformance import find_contract, schema_validator

CONTRACT = find_contract("api-dashboard.yml")
Post = Callable[[Body], None]


def _get(client: TestClient, path: str, pointer: str, **params: Any) -> Any:
    response = client.get(path, params=params)
    assert response.status_code == 200, response.text
    body = response.json()
    schema_validator(CONTRACT, f"#/components/schemas/{pointer}").validate(body)
    return body


def _builds(client: TestClient, **params: Any) -> Any:
    return _get(client, "/builds", "BuildPage", **params)


def test_build_running_after_started_only(client: TestClient, post: Post) -> None:
    b = new_id()
    post(build_started(b, "2026-11-25T10:00:00Z", name="web"))
    (item,) = _builds(client)["items"]
    assert item == {
        "build_id": b,
        "pipeline_name": "web",
        "status": "running",
        "started_at": "2026-11-25T10:00:00Z",
        "finished_at": None,
        "failed_step": None,
        "failure_reason": None,
        "steps": [],
    }


def test_build_finished_before_started_still_one_build(client: TestClient, post: Post) -> None:
    b = new_id()
    post(build_finished(b, "2026-11-25T10:05:00Z"))
    (item,) = _builds(client)["items"]
    assert item["status"] == "passed"
    assert item["started_at"] is None
    assert item["finished_at"] == "2026-11-25T10:05:00Z"
    assert len(item["steps"]) == 1
    post(build_started(b, "2026-11-25T10:00:00Z"))
    (item,) = _builds(client)["items"]
    assert item["status"] == "passed"
    assert item["started_at"] == "2026-11-25T10:00:00Z"
    assert item["finished_at"] == "2026-11-25T10:05:00Z"


def test_build_failed_by_step_shows_failed_step(client: TestClient, post: Post) -> None:
    b = new_id()
    post(build_started(b))
    post(build_finished(b, outcome="failed"))
    (item,) = _builds(client)["items"]
    assert item["status"] == "failed"
    assert item["failed_step"] == "test"
    assert item["failure_reason"] is None
    assert [s["status"] for s in item["steps"]] == ["passed", "failed", "skipped"]


def test_build_failed_by_upload_shows_failure_reason(client: TestClient, post: Post) -> None:
    b = new_id()
    post(build_started(b))
    post(build_finished(b, outcome="failed", upload_failed=True))
    (item,) = _builds(client)["items"]
    assert item["status"] == "failed"
    assert item["failed_step"] is None
    assert item["failure_reason"] == "artifact upload failed"


def test_builds_newest_first_by_latest_event(client: TestClient, post: Post) -> None:
    a, b, c = new_id(), new_id(), new_id()
    post(build_started(a, "2026-11-25T10:00:00Z"))
    post(build_started(b, "2026-11-25T10:01:00Z"))
    post(build_started(c, "2026-11-25T10:02:00Z"))
    assert [i["build_id"] for i in _builds(client)["items"]] == [c, b, a]
    # a's latest event is now the newest, even though it started first
    post(build_finished(a, "2026-11-25T10:09:00Z"))
    assert [i["build_id"] for i in _builds(client)["items"]] == [a, c, b]
    # an older, late-arriving event does not move a build up
    post(build_finished(b, "2026-11-25T10:03:00Z"))
    assert [i["build_id"] for i in _builds(client)["items"]] == [a, b, c]


def test_builds_status_failed_filter(client: TestClient, post: Post) -> None:
    ok, bad, run = new_id(), new_id(), new_id()
    post(build_finished(ok, "2026-11-25T10:01:00Z"))
    post(build_finished(bad, "2026-11-25T10:02:00Z", outcome="failed"))
    post(build_started(run, "2026-11-25T10:03:00Z"))
    assert [i["build_id"] for i in _builds(client, status="failed")["items"]] == [bad]
    assert [i["build_id"] for i in _builds(client, status="passed")["items"]] == [ok]
    assert [i["build_id"] for i in _builds(client, status="running")["items"]] == [run]
    assert len(_builds(client)["items"]) == 3
    response = client.get("/builds", params={"status": "weird"})
    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["location"] == "query.status"


def test_artifacts_newest_first_by_uploaded_at(client: TestClient, post: Post) -> None:
    post(artifact_uploaded("a", 1, "2026-11-25T10:00:00Z"))
    post(artifact_uploaded("b", 1, "2026-11-25T10:02:00Z"))
    post(artifact_uploaded("a", 2, "2026-11-25T10:01:00Z"))
    items = _get(client, "/artifacts", "ArtifactPage")["items"]
    assert [(i["name"], i["version"]) for i in items] == [("b", 1), ("a", 2), ("a", 1)]


def test_artifact_of_failed_build_is_listed(client: TestClient, post: Post) -> None:
    # #131 option (a): a failed build (upload failed after the artifact was stored) may show it
    b = new_id()
    post(artifact_uploaded("api", 1, "2026-11-25T10:04:00Z", build_id=b))
    post(build_finished(b, "2026-11-25T10:05:00Z", outcome="failed", upload_failed=True))
    items = _get(client, "/artifacts", "ArtifactPage")["items"]
    assert [i["build_id"] for i in items] == [b]
    assert _builds(client)["items"][0]["status"] == "failed"


def test_release_pending_shows_requested_by(client: TestClient, post: Post) -> None:
    r = new_id()
    post(release_requested(r, by="sam"))
    (item,) = _get(client, "/releases", "ReleasePage")["items"]
    assert item == {
        "release_id": r,
        "artifact": {"name": "api", "version": 1},
        "status": "pending",
        "requested_by": "sam",
        "requested_at": "2026-11-25T10:10:00Z",
        "decided_by": None,
        "decided_at": None,
    }
    post(release_decided(r, "2026-11-25T10:20:00Z", "rejected"))
    (item,) = _get(client, "/releases", "ReleasePage")["items"]
    assert item["status"] == "rejected"
    assert item["requested_by"] == "sam"
    assert item["decided_by"] == "dana"


def test_release_decided_before_requested_has_null_requested_by(
    client: TestClient, post: Post
) -> None:
    r = new_id()
    post(release_decided(r, "2026-11-25T10:20:00Z"))
    (item,) = _get(client, "/releases", "ReleasePage")["items"]
    assert item["status"] == "approved"
    assert item["requested_by"] is None
    assert item["requested_at"] is None
    post(release_requested(r, "2026-11-25T10:10:00Z", by="sam"))
    (item,) = _get(client, "/releases", "ReleasePage")["items"]
    assert item["requested_by"] == "sam"
    assert item["status"] == "approved"


def test_releases_newest_first_by_latest_event(client: TestClient, post: Post) -> None:
    a, b = new_id(), new_id()
    post(release_requested(a, "2026-11-25T10:00:00Z"))
    post(release_requested(b, "2026-11-25T10:01:00Z"))
    post(release_decided(a, "2026-11-25T10:05:00Z"))
    ids = [i["release_id"] for i in _get(client, "/releases", "ReleasePage")["items"]]
    assert ids == [a, b]


def test_release_view_has_no_promotion_field(client: TestClient, post: Post) -> None:
    post(release_requested(new_id()))
    (item,) = _get(client, "/releases", "ReleasePage")["items"]
    assert "promotion" not in item and "promoted" not in item and "promoted_at" not in item
    assert set(item) == {
        "release_id",
        "artifact",
        "status",
        "requested_by",
        "requested_at",
        "decided_by",
        "decided_at",
    }


def test_limit_above_200_is_422(client: TestClient) -> None:
    for path in ("/builds", "/artifacts", "/releases"):
        response = client.get(path, params={"limit": 201})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_failed"
        assert response.json()["error"]["details"][0]["location"] == "query.limit"
        assert client.get(path, params={"limit": 0}).status_code == 422
        assert client.get(path, params={"offset": -1}).status_code == 422
        assert client.get(path, params={"limit": 200}).status_code == 200


def test_limit_and_offset_page(client: TestClient, post: Post) -> None:
    ids = [new_id() for _ in range(5)]
    for n, b in enumerate(ids):
        post(build_started(b, f"2026-11-25T10:0{n}:00Z"))
    newest_first = list(reversed(ids))
    page = _builds(client, limit=2, offset=1)
    assert (page["limit"], page["offset"]) == (2, 1)
    assert [i["build_id"] for i in page["items"]] == newest_first[1:3]
    assert _builds(client, offset=10)["items"] == []
    default = _builds(client)
    assert (default["limit"], default["offset"]) == (50, 0)
    for n in range(3):
        post(artifact_uploaded("a", n + 1, f"2026-11-25T10:0{n}:00Z"))
        post(release_requested(new_id(), f"2026-11-25T10:0{n}:00Z"))
    assert len(_get(client, "/artifacts", "ArtifactPage", limit=2)["items"]) == 2
    assert len(_get(client, "/releases", "ReleasePage", limit=1, offset=2)["items"]) == 1


def test_empty_views_are_pages_with_empty_lists(client: TestClient) -> None:
    assert _builds(client)["items"] == []
    assert _get(client, "/artifacts", "ArtifactPage")["items"] == []
    assert _get(client, "/releases", "ReleasePage")["items"] == []


def test_every_response_validates_against_contract_schema(client: TestClient, post: Post) -> None:
    b1, b2, b3, r1, r2 = (new_id() for _ in range(5))
    post(build_started(b1))
    post(build_finished(b2, outcome="failed"))
    post(build_finished(b3, outcome="failed", upload_failed=True))
    post(build_finished(new_id()))
    post(artifact_uploaded())
    post(release_requested(r1))
    post(release_decided(r2))
    counts = {None: 4, "running": 1, "passed": 1, "failed": 2}
    for status, count in counts.items():
        params = {} if status is None else {"status": status}
        assert len(_builds(client, **params)["items"]) == count
    assert len(_builds(client)["items"]) == 4
    assert len(_get(client, "/artifacts", "ArtifactPage")["items"]) == 1
    assert len(_get(client, "/releases", "ReleasePage")["items"]) == 2


def test_get_events_after_restart_keeps_data(tmp_path: Any, monkeypatch: Any) -> None:
    """Data lives in the database file, not in memory; the startup creates the tables."""
    from app.main import app
    from app.repos import engine as engine_module

    monkeypatch.setenv("DASHBOARD_DATABASE_URL", f"sqlite:///{tmp_path}/sub/d.db")
    for _ in range(2):
        engine_module.get_engine.cache_clear()
        with TestClient(app) as client:
            if _ == 0:
                assert client.post("/events", json=build_started(new_id())).status_code == 202
            else:
                assert len(client.get("/builds").json()["items"]) == 1
    engine_module.get_engine.cache_clear()

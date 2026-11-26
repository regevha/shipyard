import copy
from collections.abc import Callable
from typing import Any

import pytest
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


def _all_events() -> list[Body]:
    return [
        build_started(new_id()),
        build_finished(new_id()),
        build_finished(new_id(), outcome="failed"),
        build_finished(new_id(), outcome="failed", upload_failed=True),
        artifact_uploaded(),
        release_requested(new_id()),
        release_decided(new_id(), decision="rejected"),
    ]


def test_valid_event_of_each_type_is_202(client: TestClient) -> None:
    for event in _all_events():
        response = client.post("/events", json=event)
        assert response.status_code == 202
        assert response.content == b""


def test_repeated_event_id_is_202_and_first_body_wins(client: TestClient) -> None:
    build_id = new_id()
    first = build_started(build_id, name="first")
    second = copy.deepcopy(first)
    second["data"]["pipeline_name"] = "second"
    second["occurred_at"] = "2026-11-25T11:00:00Z"
    assert client.post("/events", json=first).status_code == 202
    assert client.post("/events", json=second).status_code == 202
    items = client.get("/builds").json()["items"]
    assert len(items) == 1
    assert items[0]["pipeline_name"] == "first"
    assert items[0]["started_at"] == "2026-11-25T10:00:00Z"


def test_unknown_type_is_422(client: TestClient) -> None:
    event = build_started(new_id())
    event["type"] = "build.cancelled"
    response = client.post("/events", json=event)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


def test_source_not_matching_type_is_422(client: TestClient) -> None:
    event = build_started(new_id())
    event["source"] = "artifact-store"
    assert client.post("/events", json=event).status_code == 422


def test_unknown_field_is_422(client: TestClient) -> None:
    event = build_started(new_id())
    event["extra"] = 1
    assert client.post("/events", json=event).status_code == 422
    event = build_started(new_id())
    event["data"]["extra"] = 1
    assert client.post("/events", json=event).status_code == 422


def test_invalid_json_is_422(client: TestClient) -> None:
    response = client.post(
        "/events", content=b"{nope", headers={"content-type": "application/json"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


def test_event_timestamp_with_trailing_newline_is_422(client: TestClient) -> None:
    event = build_started(new_id())
    event["occurred_at"] = "2026-11-25T10:00:00Z\n"
    assert client.post("/events", json=event).status_code == 422
    event = build_started(new_id())
    event["data"]["pipeline_name"] = "api\n"
    assert client.post("/events", json=event).status_code == 422
    event = build_started(new_id())
    event["event_id"] += "\n"
    assert client.post("/events", json=event).status_code == 422


def _mutations() -> list[Callable[[Body], None]]:
    return [
        lambda e: e.pop("data"),
        lambda e: e.update(schema_version=2),
        lambda e: e.update(occurred_at="2026-11-25 10:00:00"),
        lambda e: e.update(occurred_at="2026-11-25T10:00:00+01:00"),
        lambda e: e.update(event_id="not-a-uuid"),
        lambda e: e["data"].update(pipeline_name="my pipeline"),
        lambda e: e["data"].update(pipeline_name="-x"),
        lambda e: e["data"].update(pipeline_name="a" * 101),
        lambda e: e["data"].pop("build_id"),
    ]


@pytest.mark.parametrize("mutate", _mutations())
def test_invalid_event_is_422_and_stores_nothing(
    client: TestClient, mutate: Callable[[Body], None]
) -> None:
    event = build_started(new_id())
    mutate(event)
    assert client.post("/events", json=event).status_code == 422
    assert client.get("/builds").json()["items"] == []


@pytest.mark.parametrize("body", [[], "x", 5, None])
def test_non_object_body_is_422(client: TestClient, body: Any) -> None:
    assert client.post("/events", json=body).status_code == 422


def test_build_finished_state_table_violations_are_422(client: TestClient) -> None:
    bad: list[Body] = []
    e = build_finished(new_id())
    e["data"]["failed_step"] = "install"
    bad.append(e)
    e = build_finished(new_id(), outcome="failed")
    e["data"]["failed_step"] = "install"  # name does not match the failed step
    bad.append(e)
    e = build_finished(new_id(), outcome="failed")
    e["data"]["failed_step"] = None
    bad.append(e)
    e = build_finished(new_id(), outcome="failed")
    e["data"]["steps"].reverse()  # skipped before failed
    bad.append(e)
    e = build_finished(new_id(), outcome="failed")
    e["data"]["steps"][0]["status"] = "skipped"  # step before the failure did not pass
    bad.append(e)
    e = build_finished(new_id(), outcome="failed", upload_failed=True)
    e["data"]["failure_reason"] = None  # failed with no step and no reason
    bad.append(e)
    e = build_finished(new_id())
    e["data"]["failure_reason"] = "artifact upload failed"  # passed with a reason
    bad.append(e)
    e = build_finished(new_id())
    e["data"]["steps"] = []
    bad.append(e)
    e = build_finished(new_id())
    e["data"]["steps"][0]["finished_at"] = None  # passed step without finish time
    bad.append(e)
    for event in bad:
        assert client.post("/events", json=event).status_code == 422, event


def test_fractional_seconds_order_correctly(
    client: TestClient, post: Callable[[Body], None]
) -> None:
    a, b = new_id(), new_id()
    post(build_started(a, "2026-11-25T10:00:00.500Z"))
    post(build_started(b, "2026-11-25T10:00:00Z"))
    ids = [i["build_id"] for i in client.get("/builds").json()["items"]]
    assert ids == [a, b]


def test_event_is_readable_right_after_202(client: TestClient) -> None:
    for _ in range(20):
        build_id = new_id()
        assert client.post("/events", json=build_started(build_id)).status_code == 202
        ids = [i["build_id"] for i in client.get("/builds", params={"limit": 200}).json()["items"]]
        assert build_id in ids

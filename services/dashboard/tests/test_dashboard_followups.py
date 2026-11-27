"""Wave 2 follow-ups: version cap (Q-40, #170), internal-error build.finished (Q-41, #167)."""

import copy
from collections.abc import Callable
from typing import Any

import pytest
from conftest import (
    STEP_FAIL,
    STEP_OK,
    STEP_SKIPPED,
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

MAX_VERSION = 2**63 - 1
Post = Callable[[Body], None]


def _check(pointer: str, body: Any) -> None:
    schema_validator(find_contract("api-dashboard.yml"), pointer).validate(body)


def _get(client: TestClient, path: str, page: str) -> list[dict[str, Any]]:
    response = client.get(path)
    assert response.status_code == 200, response.text
    _check(f"#/components/schemas/{page}", response.json())
    items: list[dict[str, Any]] = response.json()["items"]
    return items


def _locations(response: Any) -> list[str]:
    return [d["location"] for d in response.json()["error"]["details"]]


def test_q40_version_max_is_accepted_and_read_back_exactly(client: TestClient, post: Post) -> None:
    rid = new_id()
    post(artifact_uploaded(version=MAX_VERSION, at="2026-11-25T10:04:30Z"))
    post(release_requested(rid, version=MAX_VERSION))
    artifacts = _get(client, "/artifacts", "ArtifactPage")
    assert artifacts[0]["version"] == MAX_VERSION
    post(release_decided(rid, version=MAX_VERSION))
    releases = _get(client, "/releases", "ReleasePage")
    assert releases[0]["artifact"]["version"] == MAX_VERSION
    assert releases[0]["status"] == "approved"


@pytest.mark.parametrize("version", [2**63, 2**200])
def test_q40_version_above_max_is_422_and_nothing_stored(client: TestClient, version: int) -> None:
    rid = new_id()
    cases = [
        (artifact_uploaded(version=version), "body.data.version"),
        (release_requested(rid, version=version), "body.data.artifact.version"),
        (release_decided(rid, version=version), "body.data.artifact.version"),
    ]
    for event, location in cases:
        response = client.post("/events", json=event)
        assert response.status_code == 422, response.text
        assert response.json()["error"]["code"] == "validation_failed"
        assert any(loc.endswith(location[len("body") :]) for loc in _locations(response))
    assert _get(client, "/artifacts", "ArtifactPage") == []
    assert _get(client, "/releases", "ReleasePage") == []


def _steps(*statuses: str) -> list[Body]:
    out: list[Body] = []
    for i, status in enumerate(statuses):
        base = {"passed": STEP_OK, "failed": STEP_FAIL, "skipped": STEP_SKIPPED}.get(status)
        step: Body = copy.deepcopy(base) if base else {"status": status}
        if base is None:
            step.update(name=f"s{i}", started_at=None, finished_at=None)
            if status == "running":
                step["started_at"] = "2026-11-25T10:00:00Z"
        else:
            step["name"] = f"s{i}"
        out.append(step)
    return out


def _internal(steps: list[Body], failed_step: str | None = None, outcome: str = "failed") -> Body:
    event = build_finished(new_id(), outcome="failed")
    event["data"].update(
        outcome=outcome, steps=steps, failed_step=failed_step, failure_reason="internal error"
    )
    return event


@pytest.mark.parametrize(
    "statuses",
    [
        ("passed", "failed", "skipped", "skipped"),
        ("passed", "passed", "skipped"),
        ("skipped", "skipped"),
        ("passed", "failed"),
    ],
)
def test_q41_internal_error_build_finished_is_accepted_and_listed(
    client: TestClient, post: Post, statuses: tuple[str, ...]
) -> None:
    steps = _steps(*statuses)
    event = _internal(steps)
    post(build_started(event["data"]["build_id"]))
    post(event)
    items = _get(client, "/builds?status=failed", "BuildPage")
    assert len(items) == 1
    assert items[0]["failure_reason"] == "internal error"
    assert items[0]["failed_step"] is None
    assert items[0]["status"] == "failed"
    assert items[0]["steps"] == steps


def test_q41_invalid_internal_error_rows_are_422(client: TestClient) -> None:
    bad = [
        _internal(_steps("passed", "failed"), failed_step="s1"),
        _internal(_steps("passed", "failed", "failed")),
        _internal(_steps("passed", "running")),
        _internal(_steps("pending", "skipped")),
        _internal(_steps("failed", "passed")),
        _internal(_steps("skipped", "passed")),
        _internal(_steps("passed", "failed", "passed")),
        _internal(_steps("passed"), outcome="passed"),
        _internal([]),
    ]
    for event in bad:
        assert client.post("/events", json=event).status_code == 422, event
    assert _get(client, "/builds", "BuildPage") == []


def test_upload_reason_row_still_requires_every_step_passed(client: TestClient, post: Post) -> None:
    for statuses in [("passed", "failed"), ("passed", "skipped"), ("skipped",)]:
        event = build_finished(new_id(), outcome="failed", upload_failed=True)
        event["data"]["steps"] = _steps(*statuses)
        assert client.post("/events", json=event).status_code == 422, statuses
    post(build_finished(new_id(), outcome="failed", upload_failed=True))
    items = _get(client, "/builds?status=failed", "BuildPage")
    assert [i["failure_reason"] for i in items] == ["artifact upload failed"]

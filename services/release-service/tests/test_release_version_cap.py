"""Q-40 (#170): a version is 1 to 2^63-1; above that is 422, nothing stored, no event; the column is
an integer."""

from __future__ import annotations

from typing import Any

import pytest
from conftest import Fakes, decide, make_release, request_body, settle
from fastapi.testclient import TestClient
from sqlalchemy import Integer

from app.repos.tables import ReleaseRow

MAX = 2**63 - 1


def test_q40_version_max_round_trips_exactly(client: TestClient, fakes: Fakes) -> None:
    release = make_release(client, version=MAX)
    assert release["artifact"]["version"] == MAX
    rid = release["release_id"]
    assert client.get(f"/releases/{rid}").json()["artifact"]["version"] == MAX
    decided = decide(client, rid, "approved")
    assert decided.json()["artifact"]["version"] == MAX
    promoted = client.post(f"/releases/{rid}/promote")
    assert promoted.json()["artifact"]["version"] == MAX
    assert [e["data"]["artifact"]["version"] for e in fakes.events] == [MAX, MAX]
    assert [e["type"] for e in fakes.events] == ["release.requested", "release.decided"]


@pytest.mark.parametrize("version", [MAX + 1, 2**64, 2**200])
def test_q40_version_above_max_is_422_nothing_stored_no_event(
    client: TestClient, fakes: Fakes, version: int
) -> None:
    response = client.post("/releases", json=request_body(version=version))
    settle(client)
    assert response.status_code == 422
    error: dict[str, Any] = response.json()["error"]
    assert error["code"] == "validation_failed"
    assert error["details"][0]["location"] == "body.artifact.version"
    assert fakes.event_attempts == []
    with client.app.state.repo._factory() as session:  # type: ignore[attr-defined]
        assert session.query(ReleaseRow).count() == 0


def test_q40_version_column_is_integer() -> None:
    column = ReleaseRow.__table__.c.artifact_version
    assert isinstance(column.type, Integer)

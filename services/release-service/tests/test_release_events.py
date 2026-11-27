"""Events (PLAN.md Conventions, contracts/events.yml): sent after the commit, from a background
task; release.requested and release.decided only; none for a promotion (Q-14); artifact-store is
never called (Q-16)."""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

import httpx
from conftest import Fakes, decide, make_release, request_body
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openapi_conformance import find_contract, schema_validator

from app.core.config import Settings
from app.main import create_app
from app.repos.releases import ReleaseRepo


def validators() -> tuple[Any, Any]:
    contract = find_contract("events.yml")
    return (
        schema_validator(contract, "#/$defs/ReleaseRequested"),
        schema_validator(contract, "#/$defs/ReleaseDecided"),
    )


def test_release_requested_event_sent_after_commit(app: FastAPI, fakes: Fakes) -> None:
    seen: list[Any] = []
    original = fakes.dashboard

    def check_committed(request: httpx.Request) -> httpx.Response:
        repo: ReleaseRepo = app.state.repo
        import json

        rid = json.loads(request.content)["data"]["release_id"]
        seen.append(repo.get(UUID(rid)))  # a fresh session sees the committed row
        return original(request)

    fakes.dashboard = check_committed
    with TestClient(app) as client:
        release = make_release(client, requested_by="sam")
    assert len(fakes.events) == 1
    event = fakes.events[0]
    assert seen and seen[0] is not None and seen[0].status == "pending"
    requested, _ = validators()
    requested.validate(event)
    assert event["type"] == "release.requested" and event["source"] == "release-service"
    assert event["occurred_at"] == event["data"]["requested_at"] == release["requested_at"]
    assert event["data"] == {
        "release_id": release["release_id"],
        "artifact": {"name": "shipyard-api", "version": 3},
        "requested_by": "sam",
        "requested_at": release["requested_at"],
    }
    assert re.fullmatch(r"[0-9a-f-]{36}", event["event_id"])


def test_release_decided_event_sent_after_commit(app: FastAPI, fakes: Fakes) -> None:
    states: list[str] = []
    original = fakes.dashboard

    def check_committed(request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.content)
        if body["type"] == "release.decided":
            repo: ReleaseRepo = app.state.repo
            found = repo.get(UUID(body["data"]["release_id"]))
            assert found is not None
            states.append(found.status)
        return original(request)

    fakes.dashboard = check_committed
    _, decided = validators()
    with TestClient(app) as client:
        for decision in ("approved", "rejected"):
            release = make_release(client)
            response = decide(client, release["release_id"], decision, "dana")
            event = fakes.events[-1]
            decided.validate(event)
            assert event["type"] == "release.decided"
            assert event["data"]["decision"] == decision
            assert event["data"]["decided_by"] == "dana"
            assert (
                event["data"]["decided_at"] == response.json()["decided_at"] == event["occurred_at"]
            )
            assert event["data"]["artifact"] == {"name": "shipyard-api", "version": 3}
    assert states == ["approved", "rejected"]


def test_failed_decision_and_failed_request_send_no_event(client: TestClient, fakes: Fakes) -> None:
    release = make_release(client)
    decide(client, release["release_id"], "approved")
    n = len(fakes.events)
    assert decide(client, release["release_id"], "rejected").status_code == 409
    assert client.post("/releases", json={"artifact": {}}).status_code == 422
    assert client.post(f"/releases/{release['release_id']}/decision", json={}).status_code == 422
    assert len(fakes.events) == n
    assert [e["type"] for e in fakes.events] == ["release.requested", "release.decided"]


def test_q14_no_event_on_promote(client: TestClient, fakes: Fakes) -> None:
    release = make_release(client)
    decide(client, release["release_id"])
    before = list(fakes.event_attempts)
    assert client.post(f"/releases/{release['release_id']}/promote").status_code == 200
    assert client.post(f"/releases/{release['release_id']}/promote").status_code == 200
    assert client.post("/releases/" + release["release_id"] + "/promote").status_code == 200
    assert fakes.event_attempts == before
    assert all(e["type"] in {"release.requested", "release.decided"} for e in fakes.event_attempts)


def test_q16_artifact_store_never_called(client: TestClient, fakes: Fakes) -> None:
    release = make_release(client, name="does-not-exist", version=999)  # never uploaded anywhere
    decide(client, release["release_id"])
    client.post(f"/releases/{release['release_id']}/promote")
    assert fakes.hosts and set(fakes.hosts) == {"dashboard.test"}


def test_event_delivery_failure_does_not_change_release(app: FastAPI, fakes: Fakes) -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("dashboard down", request=request)

    fakes.dashboard = down
    with TestClient(app) as client:
        release = make_release(client)
        assert decide(client, release["release_id"]).status_code == 200
        assert client.post(f"/releases/{release['release_id']}/promote").status_code == 200
        got = client.get(f"/releases/{release['release_id']}").json()
    assert got["status"] == "approved" and got["promoted_at"] is not None
    assert fakes.sleeps == [0.5, 1.0, 0.5, 1.0]  # 3 attempts per event, two events


def test_sender_retries_5xx_reusing_event_id_then_succeeds(app: FastAPI, fakes: Fakes) -> None:
    calls: list[int] = []

    def flaky(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(503 if len(calls) < 3 else 202)

    fakes.dashboard = flaky
    with TestClient(app) as client:
        assert client.post("/releases", json=request_body()).status_code == 201
    assert len(fakes.event_attempts) == 3
    assert len({e["event_id"] for e in fakes.event_attempts}) == 1
    assert fakes.sleeps == [0.5, 1.0]


def test_sender_does_not_retry_4xx_and_never_raises(app: FastAPI, fakes: Fakes) -> None:
    fakes.dashboard = lambda request: httpx.Response(422)
    with TestClient(app) as client:
        assert client.post("/releases", json=request_body()).status_code == 201
    assert len(fakes.event_attempts) == 1 and fakes.sleeps == []


def test_sender_swallows_unexpected_errors(settings: Settings) -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise RuntimeError("bug")

    app = create_app(settings, httpx.MockTransport(boom), lambda _s: None)
    with TestClient(app) as client:
        assert client.post("/releases", json=request_body()).status_code == 201

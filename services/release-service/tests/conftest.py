"""Fixtures: the release-service app with the dashboard faked by an httpx.MockTransport
(contracts/api-dashboard.yml POST /events). Any other host fails the test, so no test can make a
real network call or call artifact-store (Q-16)."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

DASHBOARD_HOST = "dashboard.test"

Handler = Callable[[httpx.Request], httpx.Response]


def dashboard_accepted(request: httpx.Request) -> httpx.Response:
    return httpx.Response(202)


@dataclass
class Fakes:
    hosts: list[str] = field(default_factory=list)  # every host any request went to
    events: list[dict[str, Any]] = field(default_factory=list)  # accepted (< 500) events
    event_attempts: list[dict[str, Any]] = field(default_factory=list)
    sleeps: list[float] = field(default_factory=list)
    dashboard: Handler = dashboard_accepted

    def transport(self) -> httpx.MockTransport:
        def handle(request: httpx.Request) -> httpx.Response:
            self.hosts.append(request.url.host)
            assert request.url.host == DASHBOARD_HOST, request.url
            assert request.url.path == "/events"
            body = json.loads(request.content)
            self.event_attempts.append(body)
            response = self.dashboard(request)
            if response.status_code < 500:
                self.events.append(body)
            return response

        return httpx.MockTransport(handle)


@pytest.fixture
def fakes() -> Fakes:
    return Fakes()


@pytest.fixture
def settings() -> Settings:
    return Settings(database_url="sqlite://", dashboard_url=f"http://{DASHBOARD_HOST}")


@pytest.fixture
def app(fakes: Fakes, settings: Settings) -> FastAPI:
    return create_app(settings, fakes.transport(), fakes.sleeps.append)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as c:  # the context manager runs the lifespan (create_all)
        yield c


def request_body(
    name: str = "shipyard-api", version: int = 3, requested_by: str = "sam"
) -> dict[str, Any]:
    return {"artifact": {"name": name, "version": version}, "requested_by": requested_by}


def make_release(client: TestClient, **kwargs: Any) -> dict[str, Any]:
    response = client.post("/releases", json=request_body(**kwargs))
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def decide(
    client: TestClient, release_id: str, decision: str = "approved", by: str = "dana"
) -> httpx.Response:
    response: httpx.Response = client.post(
        f"/releases/{release_id}/decision", json={"decision": decision, "decided_by": by}
    )
    return response

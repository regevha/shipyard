"""Fixtures: the pipeline-runner app with artifact-store and the dashboard faked by one
httpx.MockTransport (contracts/api-artifact-store.yml POST /artifacts/{name}, api-dashboard.yml
POST /events). The fake records every call in order."""

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

ARTIFACT_HOST = "artifact-store.test"
DASHBOARD_HOST = "dashboard.test"

Handler = Callable[[httpx.Request], httpx.Response]


def artifact_created(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        201,
        json={
            "name": request.url.path.rsplit("/", 1)[-1],
            "version": 1,
            "checksum": request.headers.get("X-Checksum-SHA256", "0" * 64),
            "size_bytes": len(request.content),
            "build_id": request.url.params["build_id"],
            "uploaded_at": "2026-11-25T10:04:30Z",
        },
    )


def dashboard_accepted(request: httpx.Request) -> httpx.Response:
    return httpx.Response(202)


@dataclass
class Fakes:
    calls: list[str] = field(default_factory=list)  # "upload", "event:<type>" in arrival order
    uploads: list[httpx.Request] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    event_attempts: list[dict[str, Any]] = field(default_factory=list)
    sleeps: list[float] = field(default_factory=list)
    artifact: Handler = artifact_created
    dashboard: Handler = dashboard_accepted

    def transport(self) -> httpx.MockTransport:
        def handle(request: httpx.Request) -> httpx.Response:
            if request.url.host == ARTIFACT_HOST:
                self.calls.append("upload")
                self.uploads.append(request)
                return self.artifact(request)
            assert request.url.host == DASHBOARD_HOST, request.url
            assert request.url.path == "/events"

            body = json.loads(request.content)
            self.event_attempts.append(body)
            response = self.dashboard(request)
            if response.status_code < 500:
                self.calls.append(f"event:{body['type']}")
                self.events.append(body)
            return response

        return httpx.MockTransport(handle)


@pytest.fixture
def fakes() -> Fakes:
    return Fakes()


@pytest.fixture
def settings() -> Settings:
    return Settings(
        database_url="sqlite://",
        artifact_store_url=f"http://{ARTIFACT_HOST}",
        dashboard_url=f"http://{DASHBOARD_HOST}",
        upload_timeout_seconds=7.0,
        step_seconds=0,
    )


@pytest.fixture
def app(fakes: Fakes, settings: Settings) -> FastAPI:
    return create_app(settings, fakes.transport(), fakes.sleeps.append)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as c:  # the context manager runs the lifespan (create_all)
        yield c


def steps_body(*commands: str, name: str = "shipyard-api") -> dict[str, Any]:
    return {
        "name": name,
        "steps": [{"name": f"s{i}", "command": c} for i, c in enumerate(commands, 1)],
    }

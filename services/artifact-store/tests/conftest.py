import json
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.events import EventSender
from app.main import create_app

BUILD = "5d0c6f1e-2b7a-4c39-9e8d-41a2f6b3c701"


class Dashboard:
    """Fake dashboard behind httpx.MockTransport: records the events it receives."""

    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []
        self.statuses: list[int] = []  # answers in order; 202 when exhausted
        self.error: Exception | None = None
        # optional callable run on each request
        self.hook: Callable[[httpx.Request], None] | None = None
        self.calls = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        if self.hook is not None:
            self.hook(request)
        if self.error is not None:
            raise self.error
        assert request.url.path == "/events"
        self.events.append(json.loads(request.content))
        status = self.statuses.pop(0) if self.statuses else 202
        return httpx.Response(status)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        database_url="sqlite://",
        dashboard_url="http://dashboard.test",
    )


@pytest.fixture
def dashboard() -> Dashboard:
    return Dashboard()


@pytest.fixture
def sleeps() -> list[float]:
    return []


@pytest.fixture
def sender(settings: Settings, dashboard: Dashboard, sleeps: list[float]) -> EventSender:
    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)  # the waits are recorded, not slept

    return EventSender(
        settings.dashboard_url,
        transport=httpx.MockTransport(dashboard.handler),
        sleep=fake_sleep,
    )


@pytest.fixture
def client(settings: Settings, sender: EventSender) -> Iterator[TestClient]:
    with TestClient(create_app(settings, sender)) as c:
        yield c

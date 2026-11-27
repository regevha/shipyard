"""Q-42 (#171): the event sender has a 5 s total deadline, runs on the event loop and never delays a
request. No real network: the hanging dashboard is a local socket that accepts and never answers."""

from __future__ import annotations

import asyncio
import logging
import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from uuid import UUID

import httpx
import pytest
import uvicorn
from conftest import Fakes, request_body, settle
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.events import EventSender
from app.main import create_app
from app.models import ArtifactRef, Release


class HangingDashboard:
    """Listens on 127.0.0.1, accepts connections and never reads or answers."""

    def __init__(self) -> None:
        self._sock = socket.socket()
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(512)
        self.port: int = self._sock.getsockname()[1]
        self._conns: list[socket.socket] = []
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self) -> None:
        while True:
            try:
                self._conns.append(self._sock.accept()[0])
            except OSError:
                return

    def close(self) -> None:
        self._sock.close()
        for conn in self._conns:
            conn.close()


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
    return port


@contextmanager
def running_server(app: FastAPI) -> Iterator[int]:
    port = free_port()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="on")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.02)
    assert server.started
    try:
        yield port
    finally:
        server.should_exit = True
        thread.join(10)


def test_q42_hanging_dashboard_does_not_delay_other_requests(tmp_path: Path) -> None:
    hanging = HangingDashboard()
    cfg = Settings(
        database_url=f"sqlite:///{tmp_path}/r.db", dashboard_url=f"http://127.0.0.1:{hanging.port}"
    )
    app = create_app(cfg)
    try:
        with running_server(app) as port:

            async def create_80() -> list[httpx.Response]:
                async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=30) as c:
                    return list(
                        await asyncio.gather(
                            *[
                                c.post("/releases", json=request_body(version=i + 1))
                                for i in range(80)
                            ]
                        )
                    )

            responses = asyncio.run(create_80())
            assert [r.status_code for r in responses] == [201] * 80
            events: EventSender = app.state.events
            started = time.monotonic()
            got = httpx.get(
                f"http://127.0.0.1:{port}/releases/{responses[0].json()['release_id']}", timeout=30
            )
            elapsed = time.monotonic() - started
            pending = events.pending()  # the dashboard is still hanging while the GET was timed
            assert got.status_code == 200
            assert pending >= 1
            assert elapsed < 1.0, f"GET took {elapsed:.2f} s with {pending} events pending"
    finally:
        hanging.close()


def hanging_app(settings: Settings, fakes: Fakes) -> tuple[FastAPI, list[float]]:
    """An app whose dashboard never answers (the transport waits for ever)."""
    started: list[float] = []

    async def never(request: httpx.Request) -> httpx.Response:
        started.append(time.monotonic())
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    return create_app(settings, httpx.MockTransport(never), fakes.sleep), started


def test_q42_event_dropped_at_deadline(
    settings: Settings, fakes: Fakes, caplog: pytest.LogCaptureFixture
) -> None:
    # Deadline 0.6 s, attempt timeout 0.5 s, instant (fake) waits. With the deadline: attempt 1
    # runs 0.5 s, attempt 2 gets only the 0.1 s left (min(attempt timeout, time left)), and the
    # next wait would end past the deadline, so there is no third attempt: ~0.6 s in total.
    # Without a deadline: three full 0.5 s attempts, ~1.5 s.
    cfg = replace(
        settings,
        event_deadline_seconds=0.6,
        event_timeout_seconds=0.5,
        event_backoff_seconds=(0.05, 0.05),
    )
    app, attempt_starts = hanging_app(cfg, fakes)
    caplog.set_level(logging.WARNING, logger="release-service.events")
    with TestClient(app) as client:
        t0 = time.monotonic()
        assert client.post("/releases", json=request_body()).status_code == 201
        assert client.app.state.events.wait_idle(5.0)  # type: ignore[attr-defined]
        total = time.monotonic() - t0
    assert len(attempt_starts) == 2
    assert 0.55 <= total < 0.9, total
    assert attempt_starts[1] - attempt_starts[0] >= 0.45  # first attempt ran its full timeout
    assert fakes.sleeps == [0.05]  # the second wait was skipped: it would end past the deadline
    assert "dropping release.requested" in caplog.text


def test_q42_no_attempt_starts_when_the_deadline_has_passed(settings: Settings) -> None:
    # A fake clock; the wait overshoots the deadline, so the next attempt must not start.
    now = [0.0]
    attempts: list[float] = []

    def refuse(request: httpx.Request) -> httpx.Response:
        attempts.append(now[0])
        raise httpx.ConnectError("down", request=request)

    async def overshooting_sleep(seconds: float) -> None:
        now[0] += seconds + 10.0

    async def run() -> None:
        sender = EventSender(
            replace(settings, event_deadline_seconds=5.0),
            httpx.MockTransport(refuse),
            overshooting_sleep,
            lambda: now[0],
        )
        await sender.release_requested(_release())
        while sender.pending():
            await asyncio.sleep(0.01)
        await sender.close()

    asyncio.run(run())
    assert attempts == [0.0]


def _release() -> Release:
    return Release(
        release_id=UUID(int=1),
        artifact=ArtifactRef(name="a", version=1),
        status="pending",
        requested_by="s",
        requested_at="2026-11-27T00:00:00.000Z",
        decided_by=None,
        decided_at=None,
        promoted_at=None,
    )


def test_q42_retry_keeps_event_id_within_deadline(settings: Settings, fakes: Fakes) -> None:
    seen: list[str] = []

    def flaky(request: httpx.Request) -> httpx.Response:
        seen.append(request.read().decode())
        return httpx.Response(503 if len(seen) < 3 else 202)

    fakes.dashboard = flaky
    app = create_app(settings, fakes.transport(), fakes.sleep)
    with TestClient(app) as client:
        assert client.post("/releases", json=request_body()).status_code == 201
        settle(client)
    assert len(fakes.event_attempts) == 3
    assert len({e["event_id"] for e in fakes.event_attempts}) == 1
    assert fakes.sleeps == [0.5, 1.0]
    assert len(fakes.events) == 1  # the third attempt, within the 5 s deadline, was accepted


def test_q42_pending_events_are_capped(
    settings: Settings, fakes: Fakes, caplog: pytest.LogCaptureFixture
) -> None:
    cfg = replace(settings, event_pending_cap=3, event_deadline_seconds=30.0)
    app, attempt_starts = hanging_app(cfg, fakes)
    caplog.set_level(logging.WARNING, logger="release-service.events")
    with TestClient(app) as client:
        for _ in range(5):
            assert client.post("/releases", json=request_body()).status_code == 201
        events: EventSender = client.app.state.events  # type: ignore[attr-defined]
        assert events.pending() == 3  # the 4th and 5th were dropped
        assert caplog.text.count("dropping release.requested: 3 events pending") == 2


def test_q42_shutdown_cancels_pending_sends(settings: Settings, fakes: Fakes) -> None:
    app, attempt_starts = hanging_app(replace(settings, event_deadline_seconds=30.0), fakes)
    with TestClient(app) as client:
        for _ in range(5):
            assert client.post("/releases", json=request_body()).status_code == 201
        events: EventSender = client.app.state.events  # type: ignore[attr-defined]
        assert events.pending() == 5
        t0 = time.monotonic()
    assert time.monotonic() - t0 < 1.5  # lifespan exit cancelled the sends within 1 s
    assert events.pending() == 0

"""Q-42 (#171): the sender has a 5 s total deadline and never uses the handler threads."""

import asyncio
import logging
import socket
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import uvicorn
from conftest import BUILD

from app.core.config import Settings
from app.core.events import EventSender
from app.main import create_app
from app.models import Artifact


def artifact(version: int = 1) -> Artifact:
    return Artifact(
        name="app",
        version=version,
        checksum="0" * 64,
        size_bytes=1,
        build_id=BUILD,
        uploaded_at=datetime.now(UTC).replace(microsecond=0),
    )


async def settle(sender: EventSender) -> None:
    assert await asyncio.to_thread(sender.wait_idle, 10.0)


def test_q42_hanging_dashboard_does_not_delay_other_requests(tmp_path: Path) -> None:
    # a dashboard that accepts connections and never answers
    hang = socket.socket()
    hang.bind(("127.0.0.1", 0))
    hang.listen(512)
    held: list[socket.socket] = []

    def accept() -> None:
        while True:
            try:
                held.append(hang.accept()[0])
            except OSError:
                return

    threading.Thread(target=accept, daemon=True).start()
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()

    settings = Settings(
        tmp_path, f"sqlite:///{tmp_path}/a.db", f"http://127.0.0.1:{hang.getsockname()[1]}"
    )
    sender = EventSender(settings.dashboard_url)
    config = uvicorn.Config(
        create_app(settings, sender), host="127.0.0.1", port=port, log_level="error"
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.02)
        assert server.started
        with httpx.Client(base_url=base, timeout=30) as http:
            assert http.post(f"/artifacts/seed?build_id={BUILD}", content=b"x").status_code == 201
            results: list[int] = []

            def upload(i: int) -> None:
                with httpx.Client(base_url=base, timeout=30) as c:
                    r = c.post(f"/artifacts/a{i}?build_id={BUILD}", content=b"x")
                results.append(r.status_code)

            workers = [threading.Thread(target=upload, args=(i,)) for i in range(80)]
            for w in workers:
                w.start()
            for w in workers:
                w.join()
            assert results == [201] * 80
            # the dashboard is still hanging: events are pending when the GET is timed
            assert sender.pending() >= 1
            start = time.monotonic()
            r = http.get("/artifacts/seed/versions/1")
            elapsed = time.monotonic() - start
            assert sender.pending() >= 1
            assert r.status_code == 200 and r.content == b"x"
            assert elapsed < 1.0, f"unrelated GET took {elapsed:.2f} s"
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        hang.close()
        for c in held:
            c.close()
    assert not thread.is_alive()


def test_q42_event_dropped_at_deadline(caplog: pytest.LogCaptureFixture) -> None:
    calls: list[float] = []

    async def hang(request: httpx.Request) -> httpx.Response:
        calls.append(time.monotonic())
        await asyncio.sleep(3600)
        raise AssertionError("unreachable")

    sender = EventSender(
        "http://dash.test",
        httpx.MockTransport(hang),
        deadline=0.4,
        attempt_timeout=0.25,
        waits=(0.05, 0.5),
    )

    async def scenario() -> float:
        await sender.start()
        start = time.monotonic()
        sender.schedule(artifact())
        await settle(sender)
        took = time.monotonic() - start
        await sender.close()
        return took

    with caplog.at_level(logging.WARNING, logger="artifact-store.events"):
        took = asyncio.run(scenario())
    # attempt 1 (0.25 s), wait 0.05, attempt 2 capped to the 0.1 s left; the 0.5 s wait would pass
    # the deadline, so nothing more starts
    assert len(calls) == 2
    assert took < 0.4 + 0.2
    assert "dropped at the deadline" in caplog.text


def test_q42_retry_keeps_event_id_within_deadline() -> None:
    bodies: list[bytes] = []
    answers: list[int | str] = [503, "network", 202]
    waits: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(request.content)
        answer = answers.pop(0)
        if isinstance(answer, str):
            raise httpx.ConnectError("down")
        return httpx.Response(answer)

    async def fake_sleep(seconds: float) -> None:
        waits.append(seconds)

    sender = EventSender("http://dash.test", httpx.MockTransport(handler), sleep=fake_sleep)

    async def scenario() -> None:
        await sender.start()
        sender.schedule(artifact())
        await settle(sender)
        await sender.close()

    asyncio.run(scenario())
    assert len(bodies) == 3 and waits == [0.5, 1.0]
    assert len(set(bodies)) == 1  # the same event, with the same event_id, on every attempt


def test_q42_pending_events_are_capped(caplog: pytest.LogCaptureFixture) -> None:
    release = asyncio.Event
    gate: list[asyncio.Event] = []
    seen: list[bytes] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.content)
        await gate[0].wait()
        return httpx.Response(202)

    sender = EventSender("http://dash.test", httpx.MockTransport(handler), max_pending=3)

    async def scenario() -> None:
        gate.append(release())
        await sender.start()
        for i in range(5):
            sender.schedule(artifact(i + 1))
        assert sender.pending() == 3
        gate[0].set()
        await settle(sender)
        await sender.close()

    with caplog.at_level(logging.WARNING, logger="artifact-store.events"):
        asyncio.run(scenario())
    assert len(seen) == 3  # the other two were dropped
    assert caplog.text.count("events pending") == 2


def test_q42_shutdown_cancels_pending_sends(caplog: pytest.LogCaptureFixture) -> None:
    started: list[asyncio.Event] = []

    async def hang(request: httpx.Request) -> httpx.Response:
        started[0].set()
        await asyncio.sleep(3600)
        raise AssertionError("unreachable")

    sender = EventSender("http://dash.test", httpx.MockTransport(hang))

    async def scenario() -> float:
        started.append(asyncio.Event())
        await sender.start()
        for i in range(3):
            sender.schedule(artifact(i + 1))
        await started[0].wait()
        assert sender.pending() == 3
        begin = time.monotonic()
        await sender.close()
        return time.monotonic() - begin

    with caplog.at_level(logging.WARNING, logger="artifact-store.events"):
        took = asyncio.run(scenario())
    assert took < 1.0
    assert sender.pending() == 0
    assert "dropped at shutdown" in caplog.text

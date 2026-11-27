"""Q-42 (#171): the sender has a 5 s total deadline and never uses the handler threads; the runner
never waits for event delivery."""

from __future__ import annotations

import asyncio
import logging
import socket
import threading
import time
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
import uvicorn
from conftest import steps_body
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.events import EventSender
from app.main import create_app
from app.models import Run, StepResult


def make_run() -> Run:
    return Run(
        build_id=uuid4(),
        pipeline_name="p",
        status="passed",
        created_at="2026-11-27T10:00:00Z",
        finished_at="2026-11-27T10:00:01Z",
        failed_step=None,
        failure_reason=None,
        steps=[
            StepResult(
                name="a",
                status="passed",
                started_at="2026-11-27T10:00:00Z",
                finished_at="2026-11-27T10:00:01Z",
            )
        ],
    )


async def settle(sender: EventSender) -> None:
    assert await asyncio.to_thread(sender.wait_idle, 10.0)


def free_port() -> int:
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port: int = probe.getsockname()[1]
    probe.close()
    return port


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
    port = free_port()
    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/r.db",
        artifact_store_url=f"http://127.0.0.1:{free_port()}",  # closed: uploads fail fast
        dashboard_url=f"http://127.0.0.1:{hang.getsockname()[1]}",
        step_seconds=0,
    )
    sender = EventSender(settings.dashboard_url)
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(settings, events=sender), host="127.0.0.1", port=port, log_level="error"
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.02)
        assert server.started
        statuses: list[int] = []
        ids: list[str] = []

        def start(i: int) -> None:
            with httpx.Client(base_url=base, timeout=30) as c:
                r = c.post("/runs", json=steps_body("a", "b", name=f"p{i}"))
            statuses.append(r.status_code)
            ids.append(r.json()["build_id"])

        workers = [threading.Thread(target=start, args=(i,)) for i in range(80)]
        for w in workers:
            w.start()
        for w in workers:
            w.join()
        assert statuses == [202] * 80
        with httpx.Client(base_url=base, timeout=30) as http:
            # the runs' own work (steps and upload, worker threads, wave 3) is not what #171 is
            # about: wait until all 80 runs are final, then time the unrelated GET
            polling_from = time.monotonic()
            give_up = polling_from + 60
            open_runs = set(ids)
            while open_runs and time.monotonic() < give_up:
                for build_id in list(open_runs):
                    if http.get(f"/runs/{build_id}").json()["status"] != "running":
                        open_runs.discard(build_id)
                time.sleep(0.05)
            assert not open_runs
            # with the blocking sender the runs themselves waited for the hung dashboard (about
            # 13 s for these 80); now delivery is off the worker threads: about 1 s, bound 6 s
            assert time.monotonic() - polling_from < 6
            # the dashboard is still hanging: events are pending when the GET is timed
            assert sender.pending() >= 1
            start_at = time.monotonic()
            r = http.get(f"/runs/{ids[0]}")
            elapsed = time.monotonic() - start_at
            assert sender.pending() >= 1
        assert r.status_code == 200
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
        deadline=1.0,
        attempt_timeout=0.6,
        waits=(0.1, 2.0),
    )

    async def scenario() -> float:
        await sender.start()
        start = time.monotonic()
        sender.build_finished(make_run())
        await settle(sender)
        took = time.monotonic() - start
        await sender.close()
        return took

    with caplog.at_level(logging.WARNING, logger="pipeline-runner.events"):
        took = asyncio.run(scenario())
    # attempt 1 (0.6 s), wait 0.1, attempt 2 capped to the 0.3 s left (1.0 s in all; 1.3 s if the
    # attempt timeout were not capped); the 2 s wait would pass the deadline, so nothing more starts
    assert len(calls) == 2
    assert 0.9 < took < 1.15
    assert "dropped at the deadline" in caplog.text


def test_q42_no_wait_starts_past_the_deadline() -> None:
    now = [0.0]
    waits: list[float] = []
    attempts: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(now[0])
        now[0] += 0.6  # the attempt takes 0.6 s of (fake) time, then answers 503
        return httpx.Response(503)

    async def fake_sleep(seconds: float) -> None:
        waits.append(seconds)
        now[0] += seconds

    sender = EventSender(
        "http://dash.test",
        httpx.MockTransport(handler),
        deadline=1.0,
        waits=(0.3, 1.0),
        sleep=fake_sleep,
        clock=lambda: now[0],
    )

    async def scenario() -> None:
        await sender.start()
        sender.build_finished(make_run())
        await settle(sender)
        await sender.close()

    asyncio.run(scenario())
    # attempt 1 at 0 s (answers at 0.6), wait 0.3 (0.9), attempt 2 (1.5); the 1 s wait would end
    # past the deadline: it is not taken and nothing more starts
    assert attempts == pytest.approx([0.0, 0.9])
    assert waits == [0.3]


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
        sender.build_finished(make_run())
        await settle(sender)
        await sender.close()

    asyncio.run(scenario())
    assert len(bodies) == 3 and waits == [0.5, 1.0]
    assert len(set(bodies)) == 1  # the same event, with the same event_id, on every attempt


def test_q42_pending_events_are_capped(caplog: pytest.LogCaptureFixture) -> None:
    gate: list[asyncio.Event] = []
    seen: list[bytes] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.content)
        await gate[0].wait()
        return httpx.Response(202)

    sender = EventSender("http://dash.test", httpx.MockTransport(handler), max_pending=3)

    async def scenario() -> None:
        gate.append(asyncio.Event())
        await sender.start()
        for _ in range(5):
            sender.build_finished(make_run())
        assert sender.pending() == 3
        gate[0].set()
        await settle(sender)
        await sender.close()

    with caplog.at_level(logging.WARNING, logger="pipeline-runner.events"):
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
        for _ in range(3):
            sender.build_finished(make_run())
        await started[0].wait()
        assert sender.pending() == 3
        begin = time.monotonic()
        await sender.close()
        return time.monotonic() - begin

    with caplog.at_level(logging.WARNING, logger="pipeline-runner.events"):
        took = asyncio.run(scenario())
    assert took < 1.0
    assert sender.pending() == 0
    assert "dropped at shutdown" in caplog.text


def test_q42_runner_does_not_wait_for_event_delivery(tmp_path: Path) -> None:
    async def hang(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(3600)
        raise AssertionError("unreachable")

    settings = Settings(
        database_url=f"sqlite:///{tmp_path}/r.db",
        artifact_store_url="http://artifact-store.test",
        dashboard_url="http://dashboard.test",
        step_seconds=0,
    )
    sender = EventSender(settings.dashboard_url, httpx.MockTransport(hang))
    created = httpx.MockTransport(
        lambda request: httpx.Response(
            201,
            json={
                "name": "p",
                "version": 1,
                "checksum": "0" * 64,
                "size_bytes": 1,
                "build_id": request.url.params["build_id"],
                "uploaded_at": "2026-11-27T10:00:00Z",
            },
        )
    )
    app = create_app(settings, created, events=sender)
    with TestClient(app) as client:
        start = time.monotonic()
        build_id = client.post("/runs", json=steps_body("a", "b")).json()["build_id"]
        run = client.get(f"/runs/{build_id}").json()
        elapsed = time.monotonic() - start
        assert run["status"] == "passed"
        assert sender.pending() >= 1  # delivery is still hanging
        assert elapsed < 1.0

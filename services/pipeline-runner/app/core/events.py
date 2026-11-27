"""Event sender (PLAN.md Conventions, Q-42: 5 s total deadline, async).

A new event_id per event, reused on every attempt; at most 3 attempts, waiting 0.5 s then 1 s;
retry only on a network error, a timeout or a 5xx; each event has a total deadline counted from the
moment it is handed over; then log and drop. Sending never raises into the caller and never waits.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from app.core.timeutil import now_iso
from app.models import Run

log = logging.getLogger("pipeline-runner.events")

DEADLINE_SECONDS = 5.0
ATTEMPT_TIMEOUT_SECONDS = 2.0
WAITS_SECONDS = (0.5, 1.0)
MAX_PENDING = 1000
SHUTDOWN_SECONDS = 1.0


class EventSender:
    """Sends events from tasks on the server's event loop; `build_started` and `build_finished`
    return at once. They are called from the runner's worker thread: they only count the event and
    hand the send to the loop (`call_soon_threadsafe`), so a run never waits for the dashboard."""

    def __init__(
        self,
        dashboard_url: str,
        transport: httpx.AsyncBaseTransport | None = None,
        *,
        deadline: float = DEADLINE_SECONDS,
        attempt_timeout: float = ATTEMPT_TIMEOUT_SECONDS,
        waits: tuple[float, ...] = WAITS_SECONDS,
        max_pending: int = MAX_PENDING,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._url = dashboard_url.rstrip("/") + "/events"
        self._transport = transport
        self._deadline = deadline
        self._attempt_timeout = attempt_timeout
        self._waits = waits
        self._max_pending = max_pending
        self._sleep = sleep
        self._clock = clock
        self._loop: asyncio.AbstractEventLoop | None = None
        self._client: httpx.AsyncClient | None = None
        self._tasks: set[asyncio.Task[None]] = set()
        self._pending = 0
        self._cond = threading.Condition()

    async def start(self) -> None:
        """Bind to the running loop and create the one client (called from the lifespan)."""
        self._loop = asyncio.get_running_loop()
        self._client = httpx.AsyncClient(transport=self._transport, timeout=self._attempt_timeout)

    async def close(self) -> None:
        """Cancel pending sends (at most SHUTDOWN_SECONDS) and close the client."""
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.wait(tasks, timeout=SHUTDOWN_SECONDS)
            log.warning("%s pending events dropped at shutdown", len(tasks))
        if self._client is not None:
            await self._client.aclose()
        self._loop = None

    def pending(self) -> int:
        """Events waiting or in flight (a test hook)."""
        with self._cond:
            return self._pending

    def wait_idle(self, timeout: float = 10.0) -> bool:
        """Block until no send is pending (for tests and callers outside the loop)."""
        with self._cond:
            return self._cond.wait_for(lambda: self._pending == 0, timeout)

    def build_started(self, run: Run, occurred_at: str) -> None:
        self._schedule(
            "build.started",
            occurred_at,
            {"build_id": str(run.build_id), "pipeline_name": run.pipeline_name},
        )

    def build_finished(self, run: Run) -> None:
        assert run.finished_at is not None
        self._schedule(
            "build.finished",
            run.finished_at,
            {
                "build_id": str(run.build_id),
                "pipeline_name": run.pipeline_name,
                "outcome": run.status,
                "failed_step": run.failed_step,
                "failure_reason": run.failure_reason,
                "steps": [s.model_dump(mode="json") for s in run.steps],
            },
        )

    def _schedule(self, event_type: str, occurred_at: str, data: dict[str, Any]) -> None:
        """Hand the event to the loop; never raises, never waits."""
        try:
            loop = self._loop
            if loop is None:
                raise RuntimeError("sender is not started")
            with self._cond:
                if self._pending >= self._max_pending:
                    log.warning("%s event dropped: %s events pending", event_type, self._pending)
                    return
                self._pending += 1
            handed = self._clock()
            event: dict[str, Any] = {
                "event_id": str(uuid.uuid4()),
                "type": event_type,
                "schema_version": 1,
                "occurred_at": occurred_at or now_iso(),
                "source": "pipeline-runner",
                "data": data,
            }
            try:
                loop.call_soon_threadsafe(self._spawn, event, handed + self._deadline)
            except BaseException:
                self._done()
                raise
        except Exception:  # noqa: BLE001 - sending must never reach the caller
            log.exception("%s event dropped", event_type)

    def _spawn(self, event: dict[str, Any], deadline_at: float) -> None:
        task = asyncio.get_running_loop().create_task(self._run(event, deadline_at))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _done(self) -> None:
        with self._cond:
            self._pending -= 1
            self._cond.notify_all()

    async def _run(self, event: dict[str, Any], deadline_at: float) -> None:
        try:
            await self._send(event, deadline_at)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - sending must never reach the caller
            log.exception("%s event dropped", event["type"])
        finally:
            self._done()

    async def _send(self, event: dict[str, Any], deadline_at: float) -> None:
        client = self._client
        assert client is not None
        kind = event["type"]
        attempt = 0
        while True:
            left = deadline_at - self._clock()
            if left <= 0:
                log.warning("%s event dropped at the deadline (%s attempts)", kind, attempt)
                return
            attempt += 1
            try:
                async with asyncio.timeout(min(self._attempt_timeout, left)):
                    response = await client.post(self._url, json=event)
            except (httpx.TransportError, TimeoutError) as exc:
                reason = type(exc).__name__
            else:
                if response.status_code < 500:
                    if response.status_code >= 400:
                        log.warning("dashboard refused %s: %s", kind, response.status_code)
                    return
                reason = f"status {response.status_code}"
            if attempt > len(self._waits):
                log.warning("%s event dropped after %s attempts (%s)", kind, attempt, reason)
                return
            wait = self._waits[attempt - 1]
            if self._clock() + wait >= deadline_at:
                log.warning("%s event dropped at the deadline (%s)", kind, reason)
                return
            await self._sleep(wait)

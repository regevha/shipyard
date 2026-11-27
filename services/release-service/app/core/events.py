"""Event sender (PLAN.md Conventions, Q-42): a new event_id per event, reused on every attempt; a
5 s total deadline per event; each attempt's timeout is min(2 s, time left); waits 0.5 s then 1 s;
no attempt or wait starts past the deadline; retry only on a network error, a timeout or a 5xx;
then log and drop. Each send is its own asyncio task on the server's event loop with one
httpx.AsyncClient per app; scheduling never blocks and never raises into the caller. At most
`event_pending_cap` sends wait or run; one more is dropped. `close` cancels pending sends within
1 s.
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

from app.core.config import Settings
from app.models import Release

log = logging.getLogger("release-service.events")

SHUTDOWN_GRACE_SECONDS = 1.0


async def _asyncio_sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


class EventSender:
    def __init__(
        self,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings = settings
        self._sleep = sleep or _asyncio_sleep
        self._clock = clock
        self._client = httpx.AsyncClient(
            transport=transport,
            timeout=settings.event_timeout_seconds,
            limits=httpx.Limits(max_connections=settings.event_pending_cap),
        )
        self._tasks: set[asyncio.Task[None]] = set()
        self._idle = threading.Condition()

    # Test hooks -------------------------------------------------------------------------------
    def pending(self) -> int:
        """Number of sends waiting or in flight."""
        return len(self._tasks)

    def wait_idle(self, timeout: float = 10.0) -> bool:
        """Block the calling (non-loop) thread until no send is pending; False on timeout."""
        with self._idle:
            return self._idle.wait_for(lambda: not self._tasks, timeout)

    # Scheduling (async, so Starlette runs it on the loop; it only schedules and returns) -------
    async def release_requested(self, release: Release) -> None:
        self._schedule(
            "release.requested",
            release.requested_at,
            {
                "release_id": str(release.release_id),
                "artifact": release.artifact.model_dump(),
                "requested_by": release.requested_by,
                "requested_at": release.requested_at,
            },
        )

    async def release_decided(self, release: Release) -> None:
        assert release.decided_at is not None
        self._schedule(
            "release.decided",
            release.decided_at,
            {
                "release_id": str(release.release_id),
                "artifact": release.artifact.model_dump(),
                "decision": release.status,
                "decided_by": release.decided_by,
                "decided_at": release.decided_at,
            },
        )

    def _schedule(self, event_type: str, occurred_at: str, data: dict[str, Any]) -> None:
        try:
            if len(self._tasks) >= self._settings.event_pending_cap:
                log.warning("dropping %s: %d events pending", event_type, len(self._tasks))
                return
            event = {
                "event_id": str(uuid.uuid4()),
                "type": event_type,
                "schema_version": 1,
                "occurred_at": occurred_at,
                "source": "release-service",
                "data": data,
            }
            task = asyncio.get_running_loop().create_task(self._send(event))
            with self._idle:
                self._tasks.add(task)
            task.add_done_callback(self._done)
        except Exception:  # scheduling never raises into the caller
            log.exception("could not schedule %s", event_type)

    def _done(self, task: asyncio.Task[None]) -> None:
        with self._idle:
            self._tasks.discard(task)
            self._idle.notify_all()

    # Sending ------------------------------------------------------------------------------------
    async def _send(self, event: dict[str, Any]) -> None:
        try:
            await self._deliver(event)
        except asyncio.CancelledError:
            log.warning("dropping %s: shutting down", event["type"])
            raise
        except Exception:  # sending never raises
            log.exception("could not send %s", event["type"])

    async def _deliver(self, event: dict[str, Any]) -> None:
        s = self._settings
        url = f"{s.dashboard_url.rstrip('/')}/events"
        deadline = self._clock() + s.event_deadline_seconds
        attempts = len(s.event_backoff_seconds) + 1
        reason = "deadline"
        for attempt in range(attempts):
            left = deadline - self._clock()
            if left <= 0:
                break
            try:
                async with asyncio.timeout(min(s.event_timeout_seconds, left)):
                    response = await self._client.post(url, json=event)
                if response.status_code < 500:
                    if response.status_code >= 400:
                        log.warning(
                            "dashboard rejected %s: %s", event["type"], response.status_code
                        )
                    return
                reason = f"status {response.status_code}"
            except (httpx.HTTPError, TimeoutError) as exc:
                reason = type(exc).__name__
            if attempt + 1 == attempts:
                break
            wait = s.event_backoff_seconds[attempt]
            if self._clock() + wait >= deadline:
                break
            await self._sleep(wait)
        log.warning("dropping %s after the deadline or attempts (%s)", event["type"], reason)

    # Shutdown -----------------------------------------------------------------------------------
    async def close(self) -> None:
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            _, still = await asyncio.wait(tasks, timeout=SHUTDOWN_GRACE_SECONDS)
            if still:
                log.warning("%d sends did not stop within %s s", len(still), SHUTDOWN_GRACE_SECONDS)
        await self._client.aclose()

"""Sender of the artifact.uploaded event (PLAN.md Conventions, Q-42: 5 s deadline, async)."""

import asyncio
import logging
import threading
import time
import uuid
from collections.abc import Awaitable, Callable

import httpx

from app.models import Artifact

log = logging.getLogger("artifact-store.events")

DEADLINE_SECONDS = 5.0
ATTEMPT_TIMEOUT_SECONDS = 2.0
WAITS_SECONDS = (0.5, 1.0)
MAX_PENDING = 1000
SHUTDOWN_SECONDS = 1.0


class EventSender:
    """Sends events from tasks on the server's event loop; `schedule` returns at once.

    `schedule` may be called from a handler thread: it only counts the event and hands the send to
    the loop (`call_soon_threadsafe`), so the request never waits for the dashboard.
    """

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
    ) -> None:
        self._url = dashboard_url.rstrip("/") + "/events"
        self._transport = transport
        self._deadline = deadline
        self._attempt_timeout = attempt_timeout
        self._waits = waits
        self._max_pending = max_pending
        self._sleep = sleep
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
            log.warning("%s pending artifact.uploaded events dropped at shutdown", len(tasks))
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

    @staticmethod
    def build_event(artifact: Artifact) -> dict[str, object]:
        data = artifact.model_dump(mode="json")
        return {
            "event_id": str(uuid.uuid4()),
            "type": "artifact.uploaded",
            "schema_version": 1,
            "occurred_at": data["uploaded_at"],
            "source": "artifact-store",
            "data": data,
        }

    def schedule(self, artifact: Artifact) -> None:
        """Hand the event to the loop; never raises, never waits."""
        try:
            loop = self._loop
            if loop is None:
                raise RuntimeError("sender is not started")
            with self._cond:
                if self._pending >= self._max_pending:
                    log.warning("artifact.uploaded event dropped: %s events pending", self._pending)
                    return
                self._pending += 1
            handed = time.monotonic()
            event = self.build_event(artifact)
            try:
                loop.call_soon_threadsafe(self._spawn, event, handed + self._deadline)
            except BaseException:
                self._done()
                raise
        except Exception:  # noqa: BLE001 - sending must never reach the caller
            log.exception("artifact.uploaded event dropped")

    def _spawn(self, event: dict[str, object], deadline_at: float) -> None:
        task = asyncio.get_running_loop().create_task(self._run(event, deadline_at))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _done(self) -> None:
        with self._cond:
            self._pending -= 1
            self._cond.notify_all()

    async def _run(self, event: dict[str, object], deadline_at: float) -> None:
        try:
            await self._send(event, deadline_at)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - sending must never reach the caller
            log.exception("artifact.uploaded event dropped")
        finally:
            self._done()

    async def _send(self, event: dict[str, object], deadline_at: float) -> None:
        client = self._client
        assert client is not None
        attempt = 0
        while True:
            left = deadline_at - time.monotonic()
            if left <= 0:
                log.warning(
                    "artifact.uploaded event dropped at the deadline (%s attempts)", attempt
                )
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
                        log.warning("dashboard refused event: %s", response.status_code)
                    return
                reason = f"status {response.status_code}"
            if attempt > len(self._waits):
                log.warning(
                    "artifact.uploaded event dropped after %s attempts (%s)", attempt, reason
                )
                return
            wait = self._waits[attempt - 1]
            if time.monotonic() + wait >= deadline_at:
                log.warning("artifact.uploaded event dropped at the deadline (%s)", reason)
                return
            await self._sleep(wait)

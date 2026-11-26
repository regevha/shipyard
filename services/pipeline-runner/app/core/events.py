"""Event sender (PLAN.md Conventions): new event_id per event, reused on every retry; up to 3
attempts with a 2 s timeout, waiting 0.5 s then 1 s; retry only on a network error, a timeout or a
5xx; then log and drop. Sending never raises into the caller."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from typing import Any

import httpx

from app.core.config import Settings
from app.core.timeutil import now_iso
from app.models import Run

log = logging.getLogger("pipeline-runner.events")


class EventSender:
    def __init__(
        self,
        settings: Settings,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._settings = settings
        self._transport = transport
        self._sleep = sleep

    def build_started(self, run: Run, occurred_at: str) -> None:
        self._send(
            "build.started",
            occurred_at,
            {"build_id": str(run.build_id), "pipeline_name": run.pipeline_name},
        )

    def build_finished(self, run: Run) -> None:
        assert run.finished_at is not None
        self._send(
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

    def _send(self, event_type: str, occurred_at: str, data: dict[str, Any]) -> None:
        event = {
            "event_id": str(uuid.uuid4()),
            "type": event_type,
            "schema_version": 1,
            "occurred_at": occurred_at or now_iso(),
            "source": "pipeline-runner",
            "data": data,
        }
        try:
            self._deliver(event)
        except Exception:  # sending never raises into the caller
            log.exception("could not send %s", event_type)

    def _deliver(self, event: dict[str, Any]) -> None:
        s = self._settings
        url = f"{s.dashboard_url.rstrip('/')}/events"
        attempts = len(s.event_backoff_seconds) + 1
        with httpx.Client(transport=self._transport, timeout=s.event_timeout_seconds) as client:
            for attempt in range(attempts):
                try:
                    response = client.post(url, json=event)
                    if response.status_code < 500:
                        if response.status_code >= 400:
                            log.warning(
                                "dashboard rejected %s: %s", event["type"], response.status_code
                            )
                        return
                    reason = f"status {response.status_code}"
                except httpx.HTTPError as exc:
                    reason = type(exc).__name__
                if attempt + 1 < attempts:
                    self._sleep(s.event_backoff_seconds[attempt])
                else:
                    log.warning(
                        "dropping %s after %d attempts (%s)", event["type"], attempts, reason
                    )

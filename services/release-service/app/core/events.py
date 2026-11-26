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
from app.models import Release

log = logging.getLogger("release-service.events")


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

    def release_requested(self, release: Release) -> None:
        self._send(
            "release.requested",
            release.requested_at,
            {
                "release_id": str(release.release_id),
                "artifact": release.artifact.model_dump(),
                "requested_by": release.requested_by,
                "requested_at": release.requested_at,
            },
        )

    def release_decided(self, release: Release) -> None:
        assert release.decided_at is not None
        self._send(
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

    def _send(self, event_type: str, occurred_at: str, data: dict[str, Any]) -> None:
        event = {
            "event_id": str(uuid.uuid4()),
            "type": event_type,
            "schema_version": 1,
            "occurred_at": occurred_at,
            "source": "release-service",
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

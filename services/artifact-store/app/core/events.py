"""Sender of the artifact.uploaded event (PLAN.md Conventions: 3 attempts, 2 s each)."""

import logging
import time
import uuid
from collections.abc import Callable

import httpx

from app.models import Artifact

log = logging.getLogger("artifact-store.events")

ATTEMPTS = 3
TIMEOUT_SECONDS = 2.0
BACKOFF_SECONDS = (0.5, 1.0)


class EventSender:
    def __init__(
        self,
        dashboard_url: str,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._url = dashboard_url.rstrip("/") + "/events"
        self._transport = transport
        self._sleep = sleep

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

    def send_uploaded(self, artifact: Artifact) -> None:
        """Send the event; never raises. The event_id is the same on every retry."""
        try:
            self._send(self.build_event(artifact))
        except Exception:  # noqa: BLE001 - sending must never reach the caller
            log.exception("artifact.uploaded event dropped")

    def _send(self, event: dict[str, object]) -> None:
        with httpx.Client(transport=self._transport, timeout=TIMEOUT_SECONDS) as client:
            for attempt in range(ATTEMPTS):
                try:
                    response = client.post(self._url, json=event)
                except httpx.TransportError as exc:
                    reason = type(exc).__name__
                else:
                    if response.status_code < 500:
                        if response.status_code >= 400:
                            log.warning("dashboard refused event: %s", response.status_code)
                        return
                    reason = f"status {response.status_code}"
                if attempt + 1 < ATTEMPTS:
                    self._sleep(BACKOFF_SECONDS[attempt])
                else:
                    log.warning(
                        "artifact.uploaded event dropped after %s attempts (%s)", ATTEMPTS, reason
                    )

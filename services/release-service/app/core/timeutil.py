from __future__ import annotations

from datetime import UTC, datetime


def now_iso() -> str:
    """UTC timestamp like 2026-11-25T10:00:00.123Z (events.yml Timestamp: date-time ending in Z)."""
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")

"""artifact-store down: a passing pipeline fails with "artifact upload failed" (Q-36, #120).

Stops artifact-store through its pid file (SIGTERM), so this module runs after every other test
(marker, sorted last in conftest.py); stop-stack.sh at session end accepts the dead pid file.
"""

from __future__ import annotations

import os
import signal
from typing import Any

import pytest

from stack import Stack, poll, port_open

pytestmark = pytest.mark.stops_artifact_store  # registered and sorted last in conftest.py


def stop_artifact_store(stack: Stack) -> None:
    pid = int((stack.data_dir / "artifact-store.pid").read_text().strip())
    os.kill(pid, signal.SIGTERM)

    def gone() -> bool | None:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return not port_open(stack.urls["artifact-store"]) or None
        return None

    poll(gone, 15, "artifact-store to exit and free its port")


def test_upload_failure_fails_build_with_reason(stack: Stack) -> None:
    stop_artifact_store(stack)

    accepted = stack.start_run("shipyard-upload", [("install", "pip install"), ("test", "pytest")])
    build_id = accepted["build_id"]
    # A refused connection fails at once; 30 s still covers the runner's 10 s upload timeout.
    run: dict[str, Any] = stack.wait_run(build_id, timeout=30)
    assert run["status"] == "failed"
    assert run["failed_step"] is None
    assert run["failure_reason"] == "artifact upload failed"
    assert [s["status"] for s in run["steps"]] == ["passed", "passed"]

    view = stack.wait_dashboard(
        "builds", lambda b: b["build_id"] == build_id and b["status"] == "failed", status="failed"
    )
    assert view["failed_step"] is None
    assert view["failure_reason"] == "artifact upload failed"
    assert view["steps"] == run["steps"]
    assert all(a["build_id"] != build_id for a in stack.dashboard_items("artifacts"))

    # No retry (#120): still failed a little later.
    poll(lambda: None if port_open(stack.urls["artifact-store"]) else True, 1, "store stays down")
    again = stack.call("pipeline-runner", "GET", f"/runs/{build_id}").json()
    assert again == run

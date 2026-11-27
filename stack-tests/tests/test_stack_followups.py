"""Wave 2 follow-ups through the real stack (T034): the version cap (Q-40, #170) and a dashboard
that accepts connections and never answers (Q-42, #171).

#167 (Q-41, an unexpected error in a run) cannot be provoked from outside a service; T033's unit
tests cover it. Every response goes through the contract checker.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import signal
import sqlite3
import statistics
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest

from stack import Stack, poll

MAX_VERSION = 2**63 - 1  # 9223372036854775807, events.yml#/$defs/ArtifactVersion maximum
TOO_BIG = 2**63

WRITES = 80  # concurrent writes per service (the #171 scenario)
GET_LIMIT = 1.0  # seconds an unrelated GET may take while the events hang (spec)
# The timed GET must finish this soon after the last write answered, so the events handed to the
# sender with the last writes are still inside their 5 s deadline (pending) when the GET runs.
PENDING_WINDOW = 4.0
# pipeline-runner: bursts per condition. Its own steps and uploads share the handler threads
# (Q-42 follow-up), so one GET under the same burst varied from 0.01 s to 2.5 s on this machine
# with the dashboard running. The baseline is the slowest of five such GETs (the runner's own
# delay), the stopped value the median of five, so a slow GET or two cannot fail the case. Without
# the #171 fix the stopped GET took 12.8 s against a 3.3 s baseline, far over baseline + 1.0 s.
RUNNER_ROUNDS = 5


# --------------------------------------------------------------------------- helpers
def read_db(path: Path, sql: str, *args: Any) -> list[tuple[Any, ...]]:
    """Read-only look into a service's SQLite file (proves "nothing stored")."""
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)
    try:
        return conn.execute(sql, args).fetchall()
    finally:
        conn.close()


def event(kind: str, source: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": str(uuid.uuid4()),
        "type": kind,
        "schema_version": 1,
        "occurred_at": "2026-11-27T10:00:00Z",
        "source": source,
        "data": data,
    }


def assert_validation_failed(r: httpx.Response, location_tail: str) -> None:
    assert r.status_code == 422, r.text
    error = r.json()["error"]
    assert error["code"] == "validation_failed", error
    locations = [d["location"] for d in error["details"]]
    assert any(loc.endswith(location_tail) for loc in locations), locations


# --------------------------------------------------------------------------- Q-40
def test_q40_version_cap_end_to_end(stack: Stack) -> None:
    name = "cap-edge"
    max_text = str(MAX_VERSION)

    # release-service: 2^63-1 is accepted and read back exactly (201, GET, decision, promote).
    r = stack.call(
        "release-service",
        "POST",
        "/releases",
        json={"artifact": {"name": name, "version": MAX_VERSION}, "requested_by": "sam"},
    )
    assert r.status_code == 201, r.text
    assert max_text in r.text  # an exact JSON integer, not a float
    rid = r.json()["release_id"]
    assert r.json()["artifact"] == {"name": name, "version": MAX_VERSION}
    got = stack.call("release-service", "GET", f"/releases/{rid}")
    assert got.status_code == 200 and got.json()["artifact"]["version"] == MAX_VERSION
    decided = stack.call(
        "release-service",
        "POST",
        f"/releases/{rid}/decision",
        json={"decision": "approved", "decided_by": "dana"},
    )
    assert decided.status_code == 200 and decided.json()["artifact"]["version"] == MAX_VERSION
    promoted = stack.call("release-service", "POST", f"/releases/{rid}/promote")
    assert promoted.status_code == 200 and promoted.json()["artifact"]["version"] == MAX_VERSION

    # The dashboard got release.requested and release.decided and shows the exact version
    # (it answered 500 for such an event before T030, so the release never reached it).
    view = stack.wait_dashboard(
        "releases", lambda x: x["release_id"] == rid and x["status"] == "approved"
    )
    assert view["artifact"] == {"name": name, "version": MAX_VERSION}
    page = stack.call("dashboard", "GET", "/releases", params={"limit": 200})
    assert max_text in page.text

    # release-service: 2^63 is 422 validation_failed and nothing is stored, no event is sent.
    big_name = "cap-too-big"
    r = stack.call(
        "release-service",
        "POST",
        "/releases",
        json={"artifact": {"name": big_name, "version": TOO_BIG}, "requested_by": "sam"},
    )
    assert_validation_failed(r, "artifact.version")
    rows = read_db(
        stack.data_dir / "release_service.db",
        "SELECT count(*) FROM releases WHERE artifact_name = ?",
        big_name,
    )
    assert rows == [(0,)], "release-service stored a release above the cap"

    # artifact-store: 2^63-1 is a valid version (404, never stored); 2^63 is 422 (was 404).
    r = stack.call("artifact-store", "GET", f"/artifacts/{name}/versions/{MAX_VERSION}")
    assert r.status_code == 404, r.text
    r = stack.call("artifact-store", "GET", f"/artifacts/{name}/versions/{TOO_BIG}")
    assert_validation_failed(r, "version")
    # A stored name too: the cap check comes before the lookup.
    body = b"cap bytes\n"
    up = stack.call(
        "artifact-store",
        "POST",
        f"/artifacts/{name}?build_id={uuid.uuid4()}",
        content=body,
        headers={"content-type": "application/octet-stream"},
    )
    assert up.status_code == 201, up.text
    r = stack.call("artifact-store", "GET", f"/artifacts/{name}/versions/{TOO_BIG}")
    assert_validation_failed(r, "version")

    # dashboard POST /events: 2^63-1 accepted and listed exactly; 2^63 is 422, nothing stored.
    build_id = str(uuid.uuid4())
    artifact = {
        "name": "cap-event",
        "version": MAX_VERSION,
        "checksum": hashlib.sha256(b"x").hexdigest(),
        "size_bytes": 1,
        "build_id": build_id,
        "uploaded_at": "2026-11-27T10:00:00Z",
    }
    ok = event("artifact.uploaded", "artifact-store", artifact)
    r = stack.call("dashboard", "POST", "/events", json=ok)
    assert r.status_code == 202, r.text
    listed = stack.wait_dashboard("artifacts", lambda a: a["build_id"] == build_id)
    assert listed["version"] == MAX_VERSION

    big_build = str(uuid.uuid4())
    too_big_events = [
        event(
            "artifact.uploaded",
            "artifact-store",
            {**artifact, "name": "cap-event-big", "version": TOO_BIG, "build_id": big_build},
        ),
        event(
            "release.requested",
            "release-service",
            {
                "release_id": str(uuid.uuid4()),
                "artifact": {"name": "cap-event-big", "version": TOO_BIG},
                "requested_by": "sam",
                "requested_at": "2026-11-27T10:00:00Z",
            },
        ),
        event(
            "release.decided",
            "release-service",
            {
                "release_id": str(uuid.uuid4()),
                "artifact": {"name": "cap-event-big", "version": TOO_BIG},
                "decision": "approved",
                "decided_by": "dana",
                "decided_at": "2026-11-27T10:00:00Z",
            },
        ),
    ]
    for bad in too_big_events:
        r = stack.call("dashboard", "POST", "/events", json=bad)
        assert_validation_failed(r, "version")
    dashboard_db = stack.data_dir / "dashboard.db"
    ids = [e["event_id"] for e in too_big_events]
    stored = read_db(dashboard_db, "SELECT count(*) FROM events WHERE event_id IN (?, ?, ?)", *ids)
    assert stored == [(0,)], "the dashboard stored an event above the cap"
    assert read_db(
        dashboard_db, "SELECT count(*) FROM artifacts WHERE name = ?", "cap-event-big"
    ) == [(0,)]
    assert read_db(
        dashboard_db, "SELECT count(*) FROM releases WHERE artifact_name = ?", "cap-event-big"
    ) == [(0,)]
    assert all(a["name"] != "cap-event-big" for a in stack.dashboard_items("artifacts"))
    assert all(x["artifact"]["name"] != "cap-event-big" for x in stack.dashboard_items("releases"))
    # The dashboard still works after them (no 500, no broken page).
    assert stack.call("dashboard", "GET", "/artifacts").status_code == 200


# --------------------------------------------------------------------------- Q-42
def dashboard_pid(stack: Stack) -> int:
    return int((stack.data_dir / "dashboard.pid").read_text().strip())


def dashboard_hangs(stack: Stack) -> bool:
    """True when the dashboard accepts the connection and does not answer within 0.5 s."""
    try:
        httpx.get(f"{stack.urls['dashboard']}/builds", timeout=httpx.Timeout(2.0, read=0.5))
    except httpx.ReadTimeout:
        return True
    return False


@contextmanager
def stopped_dashboard(stack: Stack) -> Iterator[None]:
    """SIGSTOP the dashboard; always SIGCONT it and wait until it answers again."""
    pid = dashboard_pid(stack)
    os.kill(pid, signal.SIGSTOP)
    try:
        # A stopped process keeps its listening socket: connections are accepted, never answered.
        assert dashboard_hangs(stack), "the stopped dashboard answered (or refused)"
        yield
    finally:
        os.kill(pid, signal.SIGCONT)

        def answers() -> bool | None:
            try:
                r = httpx.get(f"{stack.urls['dashboard']}/builds", timeout=5)
            except httpx.HTTPError:
                return None
            stack.contracts.check("dashboard", r)
            return True if r.status_code == 200 else None

        poll(answers, 60, "the dashboard to answer again after SIGCONT", interval=0.2)


def log_size(stack: Stack, service: str) -> int:
    return (stack.data_dir / f"{service}.log").stat().st_size


def wait_dropped(stack: Stack, service: str, offset: int) -> None:
    """The service logged an event dropped (deadline) after `offset`: the sends really hung."""

    def dropped() -> bool | None:
        with open(stack.data_dir / f"{service}.log", "rb") as f:
            f.seek(offset)
            text = f.read().decode("utf-8", "replace")
        return True if re.search(r"dropp", text) else None

    poll(dropped, 20, f"{service} to log a dropped event", interval=0.2)


async def concurrent(
    stack: Stack, service: str, make: Callable[[httpx.AsyncClient, int], Any], expect: int
) -> tuple[float, list[dict[str, Any]]]:
    """WRITES requests at once; every answer is contract-checked and `expect`. Returns the time
    (time.monotonic) at which the last one answered, and the answers' bodies."""
    limits = httpx.Limits(max_connections=WRITES, max_keepalive_connections=WRITES)
    async with httpx.AsyncClient(base_url=stack.urls[service], timeout=60, limits=limits) as client:

        async def one(i: int) -> tuple[float, dict[str, Any]]:
            r: httpx.Response = await make(client, i)
            stack.contracts.check(service, r)
            assert r.status_code == expect, r.text
            body: dict[str, Any] = r.json()
            return time.monotonic(), body

        done = await asyncio.gather(*(one(i) for i in range(WRITES)))
    return max(t for t, _ in done), [b for _, b in done]


def timed_get(stack: Stack, service: str, path: str) -> tuple[float, float]:
    """One unrelated GET; returns (seconds it took, monotonic time it ended)."""
    t0 = time.monotonic()
    # A long timeout, so a delayed GET fails on its time limit, not on the client timeout.
    r = stack.call(service, "GET", path, timeout=60)
    t1 = time.monotonic()
    assert r.status_code == 200, r.text
    return t1 - t0, t1


def burst_and_get(
    stack: Stack,
    service: str,
    make: Callable[[httpx.AsyncClient, int], Any],
    expect: int,
    get_path: str,
) -> tuple[float, float, list[dict[str, Any]]]:
    """80 concurrent writes, then the timed GET. Returns (GET seconds, seconds from the last
    write's answer to the end of the GET, the writes' answers); the caller checks the GET limit
    first, then that the GET ended inside the pending window."""
    last, bodies = asyncio.run(concurrent(stack, service, make, expect))
    took, ended = timed_get(stack, service, get_path)
    return took, ended - last, bodies


def runner_rounds(
    stack: Stack, make: Callable[[httpx.AsyncClient, int], Any], get_path: str
) -> tuple[list[float], list[float]]:
    """RUNNER_ROUNDS bursts of 80 POST /runs, each followed by the timed GET; every run of a
    burst is final on the runner before the next burst starts. Returns the GET times and, per
    burst, the seconds from the last write's answer to the end of the GET."""
    times: list[float] = []
    after: list[float] = []
    for _ in range(RUNNER_ROUNDS):
        took, after_last, runs = burst_and_get(stack, "pipeline-runner", make, 202, get_path)
        times.append(took)
        after.append(after_last)
        for run in runs:
            stack.wait_run(run["build_id"], timeout=90)
    return times, after


def assert_pending(after_last: float) -> None:
    assert after_last < PENDING_WINDOW, (
        f"the GET ended {after_last:.2f} s after the last write; events may no longer be pending"
    )


def release_body(name: str) -> dict[str, Any]:
    return {"artifact": {"name": name, "version": 1}, "requested_by": "sam"}


def run_body(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "steps": [{"name": "build", "command": "make"}, {"name": "test", "command": "pytest"}],
    }


@pytest.mark.stops_dashboard
@pytest.mark.parametrize("service", ["release-service", "artifact-store", "pipeline-runner"])
def test_q42_stopped_dashboard_does_not_delay_service(stack: Stack, service: str) -> None:
    name = f"hang-{service}"
    body = f"{service} bytes\n".encode()
    digest = hashlib.sha256(body).hexdigest()

    # An unrelated record to read while the events hang, made with the dashboard running.
    if service == "release-service":
        r = stack.call("release-service", "POST", "/releases", json=release_body("hang-probe"))
        assert r.status_code == 201, r.text
        get_path = f"/releases/{r.json()['release_id']}"

        def make(client: httpx.AsyncClient, i: int) -> Any:
            return client.post("/releases", json=release_body(name))

        expect = 201
    elif service == "artifact-store":
        r = stack.call(
            "artifact-store",
            "POST",
            f"/artifacts/hang-probe?build_id={uuid.uuid4()}",
            content=body,
            headers={"content-type": "application/octet-stream"},
        )
        assert r.status_code == 201, r.text
        get_path = f"/artifacts/hang-probe/versions/{r.json()['version']}"

        def make(client: httpx.AsyncClient, i: int) -> Any:
            # One name per upload: the burst measures the event sends, not the version
            # retries of 80 uploads racing for one name (reported separately, see T034.md).
            return client.post(
                f"/artifacts/{name}-{i}",
                params={"build_id": str(uuid.uuid4())},
                content=body,
                headers={"content-type": "application/octet-stream", "X-Checksum-SHA256": digest},
            )

        expect = 201
    else:
        probe = stack.start_run("hang-probe", [("build", "make")])
        stack.wait_run(probe["build_id"])
        get_path = f"/runs/{probe['build_id']}"

        def make(client: httpx.AsyncClient, i: int) -> Any:
            # One pipeline name per run, so the 80 uploads do not race for one artifact name's
            # next version in artifact-store (that race is reported separately, see T034.md).
            return client.post("/runs", json=run_body(f"{name}-{i}"))

        expect = 202

    if service != "pipeline-runner":
        offset = log_size(stack, service)
        with stopped_dashboard(stack):
            took, after_last, _ = burst_and_get(stack, service, make, expect, get_path)
            print(f"\n[{service}] GET with the dashboard stopped: {took:.3f} s")
            assert took < GET_LIMIT, (
                f"{service}: GET took {took:.2f} s with the dashboard stopped "
                f"(limit {GET_LIMIT:.2f} s)"
            )
            assert_pending(after_last)
            # The events really hung: the sender dropped at least one at its 5 s deadline.
            wait_dropped(stack, service, offset)
        return

    # pipeline-runner: its simulated steps and upload still run on its handler thread pool until
    # wave 3 (Q-42 follow-up), so the same bursts are timed first with the dashboard running.
    before = {b["build_id"] for b in stack.dashboard_items("builds")}
    baseline_times, _ = runner_rounds(stack, make, get_path)

    # Let the baseline settle (events delivered) before the dashboard stops.
    def settled() -> bool | None:
        mine = [
            b
            for b in stack.dashboard_items("builds")
            if b["pipeline_name"].startswith(f"{name}-") and b["build_id"] not in before
        ]
        done = sum(b["status"] != "running" for b in mine)
        return True if done >= WRITES * RUNNER_ROUNDS else None

    poll(settled, 90, "the baseline runs to finish on the dashboard", interval=0.5)

    offset = log_size(stack, service)
    with stopped_dashboard(stack):
        stopped_times, after = runner_rounds(stack, make, get_path)
        baseline = max(baseline_times)
        stopped = statistics.median(stopped_times)
        limit = baseline + GET_LIMIT
        text = (
            f"stopped {[round(t, 3) for t in stopped_times]} (median {stopped:.3f} s), "
            f"baseline {[round(t, 3) for t in baseline_times]} (slowest {baseline:.3f} s)"
        )
        print(f"\n[{service}] GET with the dashboard stopped: {text}")
        assert stopped < limit, (
            f"{service}: GET median over baseline + {GET_LIMIT} s = {limit:.2f} s: {text}"
        )
        for after_last in after:
            assert_pending(after_last)
        # The events really hung: the sender dropped at least one at its 5 s deadline.
        wait_dropped(stack, service, offset)

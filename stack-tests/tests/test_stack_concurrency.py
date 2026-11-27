"""100 runs started at once through runner -> artifact-store -> dashboard (T024 review)."""

from __future__ import annotations

import asyncio
import hashlib
import time
from typing import Any

import httpx

from stack import Stack, poll

RUNS = 100
FAIL_EVERY = 5  # every 5th run has a failing step, the rest pass and upload
NAME = "stack-load"


async def start_all(stack: Stack) -> list[tuple[dict[str, Any], bool]]:
    limits = httpx.Limits(max_connections=RUNS, max_keepalive_connections=RUNS)
    async with httpx.AsyncClient(
        base_url=stack.urls["pipeline-runner"], timeout=30, limits=limits
    ) as client:

        async def one(i: int) -> tuple[dict[str, Any], bool]:
            fails = i % FAIL_EVERY == 0
            steps = [
                {"name": "build", "command": "make"},
                {"name": "test", "command": "fail" if fails else "pytest"},
            ]
            r = await client.post("/runs", json={"name": NAME, "steps": steps})
            stack.contracts.check("pipeline-runner", r)
            assert r.status_code == 202, r.text
            run: dict[str, Any] = r.json()
            return run, fails

        return await asyncio.gather(*(one(i) for i in range(RUNS)))


def test_100_parallel_runs_reach_final_state_and_show_once(stack: Stack) -> None:
    t0 = time.monotonic()
    started = asyncio.run(start_all(stack))
    expected = {run["build_id"]: ("failed" if fails else "passed") for run, fails in started}
    assert len(expected) == RUNS, "build_ids are not unique"

    # Every run reaches its final state on the runner.
    finals: dict[str, dict[str, Any]] = {}
    for build_id in expected:
        finals[build_id] = stack.wait_run(build_id, timeout=90)
    for build_id, run in finals.items():
        assert run["status"] == expected[build_id], run
        if expected[build_id] == "failed":
            assert run["failed_step"] == "test" and run["failure_reason"] is None
        else:
            assert run["failed_step"] is None and run["failure_reason"] is None

    # The dashboard shows each build exactly once with the runner's final status.
    def all_final() -> list[dict[str, Any]] | None:
        mine = [b for b in stack.dashboard_items("builds") if b["build_id"] in expected]
        done = [b for b in mine if b["status"] != "running"]
        return mine if len(done) == RUNS else None

    views = poll(all_final, 60, f"{RUNS} final builds on the dashboard", interval=0.5)
    ids = [b["build_id"] for b in views]
    assert len(ids) == len(set(ids)) == RUNS, "a build is listed more than once"
    for b in views:
        assert b["status"] == expected[b["build_id"]], b
        assert b["steps"] == finals[b["build_id"]]["steps"]
    failed_ids = {b["build_id"] for b in stack.dashboard_items("builds", status="failed")}
    passed_ids = {b["build_id"] for b in stack.dashboard_items("builds", status="passed")}
    assert {i for i, s in expected.items() if s == "failed"} <= failed_ids
    assert {i for i, s in expected.items() if s == "passed"} <= passed_ids

    # One artifact per passed build, versions 1..n without gaps or duplicates.
    passed = {i for i, s in expected.items() if s == "passed"}

    def all_artifacts() -> list[dict[str, Any]] | None:
        mine = [a for a in stack.dashboard_items("artifacts") if a["name"] == NAME]
        return mine if len(mine) >= len(passed) else None

    artifacts = poll(all_artifacts, 60, "artifacts of every passed build", interval=0.5)
    assert sorted(a["build_id"] for a in artifacts) == sorted(passed)
    assert sorted(a["version"] for a in artifacts) == list(range(1, len(passed) + 1))
    # Spot-check the bytes of a few versions against the stored checksum.
    for a in artifacts[:5]:
        r = stack.call("artifact-store", "GET", f"/artifacts/{NAME}/versions/{a['version']}")
        assert r.status_code == 200
        assert hashlib.sha256(r.content).hexdigest() == a["checksum"]
    print(f"{RUNS} parallel runs settled in {time.monotonic() - t0:.1f} s")

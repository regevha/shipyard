from __future__ import annotations

import hashlib
from typing import Any
from uuid import UUID

import httpx
import pytest
from conftest import Fakes, steps_body
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openapi_conformance import find_contract, schema_validator

STARTED = schema_validator(find_contract("events.yml"), "events.yml#/$defs/BuildStarted")
FINISHED = schema_validator(find_contract("events.yml"), "events.yml#/$defs/BuildFinished")
RUN = schema_validator(find_contract("api-pipeline-runner.yml"), "#/components/schemas/Run")


def run_to_end(client: TestClient, body: dict[str, Any]) -> dict[str, Any]:
    build_id = client.post("/runs", json=body).json()["build_id"]
    run: dict[str, Any] = client.get(f"/runs/{build_id}").json()
    RUN.validate(run)
    return run


def statuses(run: dict[str, Any]) -> list[str]:
    return [s["status"] for s in run["steps"]]


def test_q33_command_fail_fails_step_and_skips_the_rest(client: TestClient, fakes: Fakes) -> None:
    run = run_to_end(client, steps_body("ok", "fail", "later"))
    assert statuses(run) == ["passed", "failed", "skipped"]
    assert run["status"] == "failed"
    assert run["failed_step"] == "s2"
    assert run["failure_reason"] is None
    assert run["finished_at"] == run["steps"][1]["finished_at"]
    assert run["steps"][2]["started_at"] is None


def test_q33_first_failing_step_wins(client: TestClient) -> None:
    run = run_to_end(client, steps_body("fail", "fail"))
    assert statuses(run) == ["failed", "skipped"]
    assert run["failed_step"] == "s1"


@pytest.mark.parametrize("command", ["FAIL", " fail", "fail now", "fail\n", "failed", "echo fail"])
def test_q33_only_exact_fail_fails(client: TestClient, command: str) -> None:
    run = run_to_end(client, steps_body(command))
    assert run["status"] == "passed"
    assert statuses(run) == ["passed"]


def test_q34_passed_build_uploads_one_artifact_named_after_pipeline(
    client: TestClient, fakes: Fakes
) -> None:
    run = run_to_end(client, steps_body("a", "b", name="Web_2.1"))
    assert run["status"] == "passed"
    assert len(fakes.uploads) == 1
    request = fakes.uploads[0]
    assert request.method == "POST"
    assert request.url.path == "/artifacts/Web_2.1"
    assert request.url.params["build_id"] == run["build_id"]
    assert request.headers["X-Checksum-SHA256"] == hashlib.sha256(request.content).hexdigest()
    assert request.headers["Content-Type"] == "application/octet-stream"
    assert len(request.content) > 0
    assert run["failed_step"] is None and run["failure_reason"] is None
    assert run["finished_at"] is not None


def test_q34_failed_step_uploads_nothing(client: TestClient, fakes: Fakes) -> None:
    run_to_end(client, steps_body("a", "fail"))
    assert fakes.uploads == []
    assert fakes.calls == ["event:build.started", "event:build.finished"]


def test_q36_upload_happens_while_running_and_before_build_finished(
    client: TestClient, app: FastAPI, fakes: Fakes
) -> None:
    seen: list[dict[str, Any]] = []

    def artifact(request: httpx.Request) -> httpx.Response:
        run = app.state.repo.get(UUID(request.url.params["build_id"]))
        assert run is not None
        seen.append(run.model_dump(mode="json"))
        return httpx.Response(201, json={})

    fakes.artifact = artifact
    run = run_to_end(client, steps_body("a", "b"))
    assert fakes.calls == ["event:build.started", "upload", "event:build.finished"]
    assert len(seen) == 1
    assert seen[0]["status"] == "running"
    assert seen[0]["finished_at"] is None
    assert [s["status"] for s in seen[0]["steps"]] == ["passed", "passed"]
    finished = fakes.events[-1]
    assert finished["occurred_at"] == run["finished_at"]
    assert finished["data"]["outcome"] == "passed"


@pytest.mark.parametrize("status", [200, 202, 400, 404, 413, 422, 500, 503])
def test_q36_upload_non_201_fails_build_with_reason(
    client: TestClient, fakes: Fakes, status: int
) -> None:
    fakes.artifact = lambda request: httpx.Response(status)
    run = run_to_end(client, steps_body("a", "b"))
    assert_upload_failed(run, fakes)


def assert_upload_failed(run: dict[str, Any], fakes: Fakes) -> None:
    assert run["status"] == "failed"
    assert run["failed_step"] is None
    assert run["failure_reason"] == "artifact upload failed"
    assert all(s == "passed" for s in statuses(run))
    assert run["finished_at"] is not None
    finished = fakes.events[-1]
    assert finished["type"] == "build.finished"
    assert finished["data"]["outcome"] == "failed"
    assert finished["data"]["failure_reason"] == "artifact upload failed"
    assert finished["data"]["failed_step"] is None
    FINISHED.validate(finished)


def test_q36_upload_timeout_fails_build_with_reason(client: TestClient, fakes: Fakes) -> None:
    timeouts: list[Any] = []

    def artifact(request: httpx.Request) -> httpx.Response:
        timeouts.append(request.extensions["timeout"])
        raise httpx.ReadTimeout("too slow", request=request)

    fakes.artifact = artifact
    run = run_to_end(client, steps_body("a"))
    assert_upload_failed(run, fakes)
    # the configured upload timeout (7 s in the fixture) is applied to the request
    assert timeouts == [{"connect": 7.0, "read": 7.0, "write": 7.0, "pool": 7.0}]


def test_q36_upload_network_error_fails_build_with_reason(client: TestClient, fakes: Fakes) -> None:
    def artifact(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    fakes.artifact = artifact
    assert_upload_failed(run_to_end(client, steps_body("a")), fakes)


def test_q36_upload_attempted_exactly_once(client: TestClient, fakes: Fakes) -> None:
    fakes.artifact = lambda request: httpx.Response(503)
    run_to_end(client, steps_body("a"))
    assert len(fakes.uploads) == 1
    assert fakes.sleeps == []  # no retry wait either


def test_build_started_and_build_finished_events_sent(client: TestClient, fakes: Fakes) -> None:
    run = run_to_end(client, steps_body("a", "b"))
    started, finished = fakes.events
    STARTED.validate(started)
    FINISHED.validate(finished)
    assert started["source"] == finished["source"] == "pipeline-runner"
    assert started["data"] == {"build_id": run["build_id"], "pipeline_name": "shipyard-api"}
    assert started["occurred_at"] == run["steps"][0]["started_at"]
    assert finished["occurred_at"] == run["finished_at"]
    assert finished["data"]["steps"] == run["steps"]
    assert started["event_id"] != finished["event_id"]


def test_failed_build_finished_event_validates(client: TestClient, fakes: Fakes) -> None:
    run_to_end(client, steps_body("a", "fail", "c"))
    FINISHED.validate(fakes.events[-1])
    assert fakes.events[-1]["data"]["failed_step"] == "s2"


def test_event_delivery_failure_does_not_change_outcome(client: TestClient, fakes: Fakes) -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    fakes.dashboard = down
    run = run_to_end(client, steps_body("a"))
    assert run["status"] == "passed"
    assert len(fakes.uploads) == 1
    # 3 attempts per event, same event_id on each attempt, waits 0.5 s then 1 s
    ids = [e["event_id"] for e in fakes.event_attempts]
    assert len(ids) == 6 and ids[0] == ids[1] == ids[2] and ids[3] == ids[4] == ids[5]
    assert ids[0] != ids[3]
    assert fakes.sleeps == [0.5, 1.0, 0.5, 1.0]


def test_event_5xx_is_retried_then_dropped_4xx_is_not(client: TestClient, fakes: Fakes) -> None:
    fakes.dashboard = lambda request: httpx.Response(500)
    assert run_to_end(client, steps_body("fail"))["status"] == "failed"
    assert len(fakes.event_attempts) == 6

    fakes.event_attempts.clear()
    fakes.dashboard = lambda request: httpx.Response(422)
    assert run_to_end(client, steps_body("a"))["status"] == "passed"
    assert len(fakes.event_attempts) == 2  # one attempt per event


def test_event_recovers_on_retry(client: TestClient, fakes: Fakes) -> None:
    attempts: list[int] = []

    def flaky(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        return httpx.Response(503 if len(attempts) == 1 else 202)

    fakes.dashboard = flaky
    run_to_end(client, steps_body("fail"))
    assert [e["type"] for e in fakes.events] == ["build.started", "build.finished"]
    assert fakes.sleeps == [0.5]


def test_step_seconds_delay_is_applied_per_step(fakes: Fakes, settings: Any) -> None:
    from dataclasses import replace

    from app.main import create_app

    waits: list[float] = []
    app = create_app(replace(settings, step_seconds=0.25), fakes.transport(), waits.append)
    with TestClient(app) as c:
        run_to_end(c, steps_body("a", "b"))
    assert waits == [0.25, 0.25]


def test_unexpected_error_in_background_is_logged_not_raised(
    client: TestClient, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(app.state.runner, "_upload", boom)
    run = run_to_end(client, steps_body("a"))
    assert run["status"] == "running"  # stays running; the error is only logged


def test_b1_400_concurrent_runs_all_reach_a_final_state(
    tmp_path: Any, fakes: Fakes, settings: Any
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from dataclasses import replace
    from uuid import uuid4

    from app.main import create_app
    from app.models import PipelineDefinition

    cfg = replace(settings, database_url=f"sqlite:///{tmp_path}/runner.db")
    app = create_app(cfg, fakes.transport(), fakes.sleeps.append)
    with TestClient(app):
        repo = app.state.repo
        runner = app.state.runner
        ids = []
        for i in range(400):
            commands = ("a", "fail", "c") if i % 5 == 0 else ("a", "b", "c")
            definition = PipelineDefinition.model_validate(steps_body(*commands))
            ids.append(repo.create(uuid4(), definition, "2026-11-25T10:00:00Z").build_id)
        # the real background path (Runner.execute), 40 runs at once on one file database
        with ThreadPoolExecutor(max_workers=100) as pool:
            list(pool.map(runner.execute, ids))
        runs = [repo.get(i) for i in ids]
    assert all(r is not None for r in runs)
    assert {r.status for r in runs if r} <= {"passed", "failed"}
    assert sum(r.status == "failed" for r in runs if r) == 80
    assert len(fakes.uploads) == 320
    assert sum(e["type"] == "build.finished" for e in fakes.events) == 400

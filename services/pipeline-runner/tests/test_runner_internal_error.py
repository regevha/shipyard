"""Q-41 (#167): an unexpected error in a run's background task fails the run with `internal error`;
and the one-transaction finish (a poll never sees a state the contract's Run forbids)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from conftest import Fakes, settle, steps_body
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openapi_conformance import find_contract, schema_validator
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.main import create_app
from app.models import PipelineDefinition
from app.repos.engine import init_db, make_engine
from app.repos.runs import RunRepo

STARTED = schema_validator(find_contract("events.yml"), "events.yml#/$defs/BuildStarted")
FINISHED = schema_validator(find_contract("events.yml"), "events.yml#/$defs/BuildFinished")
RUN = schema_validator(find_contract("api-pipeline-runner.yml"), "#/components/schemas/Run")


def boom(*args: Any, **kwargs: Any) -> Any:
    raise RuntimeError("boom")


def inject(app: FastAPI, stage: str, monkeypatch: pytest.MonkeyPatch) -> None:
    repo, runner = app.state.repo, app.state.runner
    if stage == "step":  # while step s2 runs: s1 passed, the write of its result fails
        original = repo.set_step

        def set_step(build_id: UUID, position: int, status: str, **kw: Any) -> None:
            if position == 1 and status == "passed":
                boom()
            original(build_id, position, status, **kw)

        monkeypatch.setattr(repo, "set_step", set_step)
    elif stage == "upload":
        monkeypatch.setattr(runner, "_upload", boom)
    elif stage == "finish":
        monkeypatch.setattr(repo, "finish", boom)
    else:
        assert stage == "before-first-step"
        monkeypatch.setattr(repo, "commands", boom)


EXPECTED_STEPS = {
    "step": ["passed", "failed", "skipped"],
    "upload": ["passed", "passed", "passed"],
    "finish": ["passed", "passed", "passed"],
    "before-first-step": ["skipped", "skipped", "skipped"],
}


@pytest.mark.parametrize("stage", ["step", "upload", "finish", "before-first-step"])
def test_q41_unexpected_error_fails_run_and_sends_build_finished(
    stage: str,
    client: TestClient,
    app: FastAPI,
    fakes: Fakes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inject(app, stage, monkeypatch)
    build_id = client.post("/runs", json=steps_body("a", "b", "c")).json()["build_id"]
    settle(client)
    run = client.get(f"/runs/{build_id}").json()
    RUN.validate(run)
    assert run["status"] == "failed"  # never left running
    assert run["failed_step"] is None
    assert run["failure_reason"] == "internal error"
    assert run["finished_at"] is not None
    assert [s["status"] for s in run["steps"]] == EXPECTED_STEPS[stage]
    if stage == "step":
        assert run["steps"][1]["finished_at"] == run["finished_at"]
        assert run["steps"][2]["started_at"] is None
    finished = [e for e in fakes.events if e["type"] == "build.finished"]
    assert len(finished) == 1  # sent once
    FINISHED.validate(finished[0])
    assert finished[0]["occurred_at"] == run["finished_at"]
    assert finished[0]["data"]["outcome"] == "failed"
    assert finished[0]["data"]["failed_step"] is None
    assert finished[0]["data"]["failure_reason"] == "internal error"
    assert finished[0]["data"]["steps"] == run["steps"]
    started = [e for e in fakes.events if e["type"] == "build.started"]
    assert len(started) == (0 if stage == "before-first-step" else 1)


@pytest.mark.parametrize("failure", ["status-500", "timeout", "network"])
def test_q41_http_upload_failure_keeps_upload_reason(
    failure: str, client: TestClient, fakes: Fakes
) -> None:
    def artifact(request: httpx.Request) -> httpx.Response:
        if failure == "status-500":
            return httpx.Response(500)
        if failure == "timeout":
            raise httpx.ReadTimeout("slow", request=request)
        raise httpx.ConnectError("refused", request=request)

    fakes.artifact = artifact
    build_id = client.post("/runs", json=steps_body("a")).json()["build_id"]
    settle(client)
    run = client.get(f"/runs/{build_id}").json()
    assert run["status"] == "failed"
    assert run["failure_reason"] == "artifact upload failed"
    finished = [e for e in fakes.events if e["type"] == "build.finished"]
    assert len(finished) == 1
    assert finished[0]["data"]["failure_reason"] == "artifact upload failed"


def test_q41_final_state_already_committed_is_kept(
    client: TestClient, app: FastAPI, fakes: Fakes, monkeypatch: pytest.MonkeyPatch
) -> None:
    # the final state is committed, then something after it fails: the run is not rewritten
    monkeypatch.setattr(app.state.events, "build_finished", boom)
    build_id = client.post("/runs", json=steps_body("a", "b")).json()["build_id"]
    settle(client)
    run = client.get(f"/runs/{build_id}").json()
    RUN.validate(run)
    assert run["status"] == "passed"
    assert run["failure_reason"] is None
    assert [s["status"] for s in run["steps"]] == ["passed", "passed"]
    assert [e["type"] for e in fakes.events] == ["build.started"]  # no second build.finished


def test_q41_fail_internal_is_a_no_op_on_a_final_run(app: FastAPI, client: TestClient) -> None:
    build_id = client.post("/runs", json=steps_body("fail")).json()["build_id"]
    settle(client)
    repo: RunRepo = app.state.repo
    assert repo.fail_internal(UUID(build_id), "2026-11-27T10:00:00Z") is None
    assert repo.fail_internal(uuid4(), "2026-11-27T10:00:00Z") is None
    run = client.get(f"/runs/{build_id}").json()
    assert run["failed_step"] == "s1" and run["failure_reason"] is None


@pytest.mark.parametrize("scenario", ["passed", "failed-step", "upload-failed", "internal-error"])
def test_every_intermediate_run_state_matches_contract(
    scenario: str,
    tmp_path: Path,
    fakes: Fakes,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = f"sqlite:///{tmp_path}/runner.db"
    cfg = replace(settings, database_url=url)
    app = create_app(cfg, fakes.transport(), fakes.sleeps.append, fakes.sender(cfg))
    reader = RunRepo(init_db(make_engine(url)))  # a second connection, as a polling GET has
    snapshots: list[dict[str, Any]] = []
    watched: list[UUID] = []

    @event.listens_for(Session, "after_commit")
    def after_commit(session: Session) -> None:
        for build_id in watched:  # read the run after every committed write
            run = reader.get(build_id)
            assert run is not None
            snapshot = run.model_dump(mode="json")
            RUN.validate(snapshot)  # raises when the contract's Run forbids this state
            snapshots.append(snapshot)

    try:
        with TestClient(app):
            repo, runner = app.state.repo, app.state.runner
            commands = ("a", "fail", "c") if scenario == "failed-step" else ("a", "b", "c")
            definition = PipelineDefinition.model_validate(steps_body(*commands))
            build_id = repo.create(uuid4(), definition, "2026-11-27T10:00:00Z").build_id
            watched.append(build_id)
            if scenario == "upload-failed":
                fakes.artifact = lambda request: httpx.Response(500)
            if scenario == "internal-error":
                monkeypatch.setattr(runner, "_upload", boom)
            runner.execute(build_id)
            assert app.state.events.wait_idle(10.0)
    finally:
        event.remove(Session, "after_commit", after_commit)
    final = snapshots[-1]
    expected = {
        "passed": ("passed", None, None),
        "failed-step": ("failed", "s2", None),
        "upload-failed": ("failed", None, "artifact upload failed"),
        "internal-error": ("failed", None, "internal error"),
    }[scenario]
    assert (final["status"], final["failed_step"], final["failure_reason"]) == expected
    assert snapshots[0]["status"] == "running"
    # every write was observed: 3 step starts + 3 results, and the final state
    assert len(snapshots) >= 7 if scenario != "failed-step" else len(snapshots) >= 4
    if scenario == "failed-step":
        # the failed step, the skipped step and the final state are one commit: the snapshot
        # after the failing step's start is followed at once by the final one
        assert [s["status"] for s in snapshots[-2]["steps"]] == ["passed", "running", "pending"]
        assert snapshots[-2]["status"] == "running"

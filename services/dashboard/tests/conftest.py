import copy
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.main import app
from app.repos.engine import get_session, init_db, make_engine

Body = dict[str, Any]
Make = Callable[..., Body]


@pytest.fixture
def engine() -> Iterator[Engine]:
    eng = make_engine("sqlite://")
    init_db(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def client(engine: Engine) -> Iterator[TestClient]:
    factory = sessionmaker(engine, expire_on_commit=False)

    def override() -> Iterator[Session]:
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


def new_id() -> str:
    return str(uuid.uuid4())


STEP_OK: Body = {
    "name": "install",
    "status": "passed",
    "started_at": "2026-11-25T10:00:00Z",
    "finished_at": "2026-11-25T10:01:00Z",
}
STEP_FAIL: Body = {**STEP_OK, "name": "test", "status": "failed"}
STEP_SKIPPED: Body = {
    "name": "package",
    "status": "skipped",
    "started_at": None,
    "finished_at": None,
}


def envelope(type_: str, source: str, occurred_at: str, data: Body) -> Body:
    return {
        "event_id": new_id(),
        "type": type_,
        "schema_version": 1,
        "occurred_at": occurred_at,
        "source": source,
        "data": data,
    }


def build_started(build_id: str, at: str = "2026-11-25T10:00:00Z", name: str = "api") -> Body:
    return envelope(
        "build.started", "pipeline-runner", at, {"build_id": build_id, "pipeline_name": name}
    )


def build_finished(
    build_id: str,
    at: str = "2026-11-25T10:05:00Z",
    outcome: str = "passed",
    name: str = "api",
    upload_failed: bool = False,
) -> Body:
    if outcome == "passed":
        steps, failed_step, reason = [STEP_OK], None, None
    elif upload_failed:
        steps, failed_step, reason = [STEP_OK], None, "artifact upload failed"
    else:
        steps, failed_step, reason = [STEP_OK, STEP_FAIL, STEP_SKIPPED], "test", None
    return envelope(
        "build.finished",
        "pipeline-runner",
        at,
        {
            "build_id": build_id,
            "pipeline_name": name,
            "outcome": outcome,
            "steps": copy.deepcopy(steps),
            "failed_step": failed_step,
            "failure_reason": reason,
        },
    )


def artifact_uploaded(
    name: str = "api", version: int = 1, at: str = "2026-11-25T10:04:30Z", build_id: str = ""
) -> Body:
    return envelope(
        "artifact.uploaded",
        "artifact-store",
        at,
        {
            "name": name,
            "version": version,
            "checksum": "a" * 64,
            "size_bytes": 10,
            "build_id": build_id or new_id(),
            "uploaded_at": at,
        },
    )


def release_requested(
    release_id: str, at: str = "2026-11-25T10:10:00Z", by: str = "sam", version: int = 1
) -> Body:
    return envelope(
        "release.requested",
        "release-service",
        at,
        {
            "release_id": release_id,
            "artifact": {"name": "api", "version": version},
            "requested_by": by,
            "requested_at": at,
        },
    )


def release_decided(
    release_id: str, at: str = "2026-11-25T10:20:00Z", decision: str = "approved", version: int = 1
) -> Body:
    return envelope(
        "release.decided",
        "release-service",
        at,
        {
            "release_id": release_id,
            "artifact": {"name": "api", "version": version},
            "decision": decision,
            "decided_by": "dana",
            "decided_at": at,
        },
    )


@pytest.fixture
def post(client: TestClient) -> Callable[[Body], None]:
    def _post(event: Body) -> None:
        response = client.post("/events", json=event)
        assert response.status_code == 202, response.text

    return _post

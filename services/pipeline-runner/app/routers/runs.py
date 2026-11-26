from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Request

from app.core.runner import Runner
from app.core.timeutil import now_iso
from app.errors import ApiError
from app.models import PipelineDefinition, Run
from app.repos.runs import RunRepo

router = APIRouter()


@router.post(
    "/runs",
    operation_id="startRun",
    status_code=202,
    response_model=Run,
    summary="Start a run of a pipeline definition",
    responses={
        202: {"description": "Run accepted; poll `GET /runs/{build_id}` for progress."},
        422: {"description": "The definition is invalid (validation_failed)."},
    },
)
def start_run(definition: PipelineDefinition, background: BackgroundTasks, request: Request) -> Run:
    repo: RunRepo = request.app.state.repo
    runner: Runner = request.app.state.runner
    build_id = uuid4()
    run = repo.create(build_id, definition, now_iso())  # committed before the response
    background.add_task(runner.execute, build_id)
    return run


@router.get(
    "/runs/{build_id}",
    operation_id="getRun",
    response_model=Run,
    summary="Status and per-step results of one run",
    responses={
        200: {"description": "The run."},
        404: {"description": "No run with this `build_id`."},
        422: {"description": "The `build_id` is not a UUID (validation_failed)."},
    },
)
def get_run(build_id: UUID, request: Request) -> Run:
    repo: RunRepo = request.app.state.repo
    run = repo.get(build_id)
    if run is None:
        raise ApiError(404, "not_found", f"run {build_id} not found")
    return run

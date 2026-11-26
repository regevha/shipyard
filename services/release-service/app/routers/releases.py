from __future__ import annotations

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, Path, Request
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from app.core.events import EventSender
from app.core.timeutil import now_iso
from app.errors import ApiError
from app.models import DecisionRequest, Release, ReleaseRequest
from app.repos.releases import ReleaseRepo

router = APIRouter()

# Contract: format uuid. Pydantic's UUID type would also accept 32 bare hex digits, braces and
# urn:uuid:, so the path is a strict hyphenated pattern (upper case allowed, as jsonschema does).
UUID_PATTERN = r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$"
ReleaseIdParam = Annotated[
    str,
    Path(
        pattern=UUID_PATTERN,
        json_schema_extra={"format": "uuid"},
        description="The release's `release_id`; a value that is not a UUID is 422.",
    ),
]


def _repo(request: Request) -> ReleaseRepo:
    repo: ReleaseRepo = request.app.state.repo
    return repo


def _events(request: Request) -> EventSender:
    events: EventSender = request.app.state.events
    return events


def _not_found(release_id: UUID) -> ApiError:
    return ApiError(404, "not_found", f"release {release_id} not found")


def existing_release(
    release_id: ReleaseIdParam, repo: Annotated[ReleaseRepo, Depends(_repo)]
) -> Release:
    """404 for an unknown id (after a malformed path is 422, before any body error)."""
    uid = UUID(release_id)
    release = repo.get(uid)
    if release is None:
        raise _not_found(uid)
    return release


async def decision_body(
    request: Request, _existing: Annotated[Release, Depends(existing_release)]
) -> DecisionRequest:
    """Read and validate the body only after the release is known to exist. FastAPI parses a JSON
    body before any dependency runs, so an unknown id with a broken body would be 422, not 404."""
    try:
        return DecisionRequest.model_validate_json(await request.body())
    except ValidationError as exc:
        raise RequestValidationError(
            [{**e, "loc": ("body", *e["loc"])} for e in exc.errors()]
        ) from exc


@router.post(
    "/releases",
    operation_id="requestRelease",
    status_code=201,
    response_model=Release,
    summary="Request a release of one artifact version",
    responses={201: {"description": "The new release."}},
)
def request_release(
    body: ReleaseRequest,
    background: BackgroundTasks,
    repo: Annotated[ReleaseRepo, Depends(_repo)],
    events: Annotated[EventSender, Depends(_events)],
) -> Release:
    release = repo.create(uuid4(), body, now_iso())  # committed before the response
    background.add_task(events.release_requested, release)
    return release


@router.get(
    "/releases/{release_id}",
    operation_id="getRelease",
    response_model=Release,
    summary="One release",
    responses={
        200: {"description": "The release."},
        404: {"description": "No release with this `release_id` (not_found)."},
    },
)
def get_release(release: Annotated[Release, Depends(existing_release)]) -> Release:
    return release


@router.post(
    "/releases/{release_id}/decision",
    operation_id="decideRelease",
    response_model=Release,
    summary="Record the approve or reject decision",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": DecisionRequest.model_json_schema()}},
        }
    },
    responses={
        200: {"description": "The release with its decision."},
        404: {"description": "No release with this `release_id` (not_found)."},
        409: {"description": "The release already has a decision (release_already_decided)."},
    },
)
def decide_release(
    release_id: ReleaseIdParam,
    body: Annotated[DecisionRequest, Depends(decision_body)],
    background: BackgroundTasks,
    repo: Annotated[ReleaseRepo, Depends(_repo)],
    events: Annotated[EventSender, Depends(_events)],
) -> Release:
    uid = UUID(release_id)
    outcome = repo.decide(uid, body.decision, body.decided_by, now_iso())
    if outcome.release is None:
        raise _not_found(uid)
    if outcome.kind == "conflict":
        raise ApiError(
            409,
            "release_already_decided",
            f"release {uid} is already {outcome.release.status}",
        )
    background.add_task(events.release_decided, outcome.release)
    return outcome.release


@router.post(
    "/releases/{release_id}/promote",
    operation_id="promoteRelease",
    response_model=Release,
    summary="Promote an approved release",
    responses={
        200: {"description": "The promoted release (unchanged when already promoted)."},
        404: {"description": "No release with this `release_id` (not_found)."},
        409: {"description": "The release is pending or rejected (release_not_approved)."},
    },
)
def promote_release(
    release_id: ReleaseIdParam, repo: Annotated[ReleaseRepo, Depends(_repo)]
) -> Release:
    uid = UUID(release_id)
    outcome = repo.promote(uid, now_iso())
    if outcome.release is None:
        raise _not_found(uid)
    if outcome.kind == "conflict":
        raise ApiError(
            409,
            "release_not_approved",
            f"release {uid} is {outcome.release.status}, not approved",
        )
    return outcome.release

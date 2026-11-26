from __future__ import annotations

from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, Request

from app.core.events import EventSender
from app.core.timeutil import now_iso
from app.errors import ApiError
from app.models import DecisionRequest, Release, ReleaseRequest
from app.repos.releases import ReleaseRepo

router = APIRouter()


def _repo(request: Request) -> ReleaseRepo:
    repo: ReleaseRepo = request.app.state.repo
    return repo


def _events(request: Request) -> EventSender:
    events: EventSender = request.app.state.events
    return events


def _not_found(release_id: UUID) -> ApiError:
    return ApiError(404, "not_found", f"release {release_id} not found")


def existing_release(release_id: UUID, repo: Annotated[ReleaseRepo, Depends(_repo)]) -> Release:
    """404 before the body is validated (error precedence of the decision operation)."""
    release = repo.get(release_id)
    if release is None:
        raise _not_found(release_id)
    return release


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
    responses={
        200: {"description": "The release with its decision."},
        404: {"description": "No release with this `release_id` (not_found)."},
        409: {"description": "The release already has a decision (release_already_decided)."},
    },
)
def decide_release(
    release_id: UUID,
    body: DecisionRequest,
    background: BackgroundTasks,
    _existing: Annotated[Release, Depends(existing_release)],
    repo: Annotated[ReleaseRepo, Depends(_repo)],
    events: Annotated[EventSender, Depends(_events)],
) -> Release:
    outcome = repo.decide(release_id, body.decision, body.decided_by, now_iso())
    if outcome.release is None:
        raise _not_found(release_id)
    if outcome.kind == "conflict":
        raise ApiError(
            409,
            "release_already_decided",
            f"release {release_id} is already {outcome.release.status}",
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
def promote_release(release_id: UUID, repo: Annotated[ReleaseRepo, Depends(_repo)]) -> Release:
    outcome = repo.promote(release_id, now_iso())
    if outcome.release is None:
        raise _not_found(release_id)
    if outcome.kind == "conflict":
        raise ApiError(
            409,
            "release_not_approved",
            f"release {release_id} is {outcome.release.status}, not approved",
        )
    return outcome.release

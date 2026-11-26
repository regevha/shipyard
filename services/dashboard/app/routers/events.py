from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.models import Event
from app.repos import events as events_repo
from app.repos.engine import get_session

router = APIRouter()


@router.post(
    "/events",
    status_code=202,
    response_class=Response,
    operation_id="receiveEvent",
    summary="Receive one event from pipeline-runner, artifact-store or release-service",
    responses={202: {"description": "Accepted (also for a repeated `event_id`). No body."}},
)
def receive_event(event: Event, session: Annotated[Session, Depends(get_session)]) -> Response:
    """Any one event of events.yml. A repeated `event_id` is 202 and changes nothing."""
    events_repo.ingest(session, event)
    return Response(status_code=202)

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.models import ArtifactPage, BuildPage, BuildStatus, ReleasePage
from app.repos import views as views_repo
from app.repos.engine import get_session

router = APIRouter()

Limit = Annotated[int, Query(ge=1, le=200, description="Page size; above 200 is 422.")]
Offset = Annotated[int, Query(ge=0, description="Number of items to skip.")]
Db = Annotated[Session, Depends(get_session)]


@router.get("/builds", operation_id="listBuilds", summary="Builds seen through events")
def list_builds(
    session: Db, limit: Limit = 50, offset: Offset = 0, status: BuildStatus | None = None
) -> BuildPage:
    """Newest first by the occurred_at of the latest event per build. `status=failed` = failures."""
    return views_repo.list_builds(session, limit, offset, status)


@router.get(
    "/artifacts", operation_id="listArtifacts", summary="Artifact versions seen through events"
)
def list_artifacts(session: Db, limit: Limit = 50, offset: Offset = 0) -> ArtifactPage:
    """Newest first by `uploaded_at`."""
    return views_repo.list_artifacts(session, limit, offset)


@router.get("/releases", operation_id="listReleases", summary="Releases and their approvals")
def list_releases(session: Db, limit: Limit = 50, offset: Offset = 0) -> ReleasePage:
    """Newest first by the occurred_at of the latest event per release."""
    return views_repo.list_releases(session, limit, offset)

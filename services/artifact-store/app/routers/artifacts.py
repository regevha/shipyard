"""POST /artifacts/{name} and GET /artifacts/{name}/versions/{version}."""

import hashlib
import tempfile
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import IO, Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Path, Query, Request
from fastapi.responses import FileResponse, Response

from app.core.config import MAX_UPLOAD_BYTES
from app.core.events import EventSender
from app.errors import ApiError
from app.models import CHECKSUM_PATTERN, NAME_PATTERN, UUID_PATTERN, Artifact
from app.repos.artifacts import ArtifactRepo

router = APIRouter()

SPOOL_MEMORY_BYTES = 1024 * 1024  # bigger bodies spill to a temporary file, never held in memory
TOO_LARGE = f"upload is larger than {MAX_UPLOAD_BYTES} bytes"

NameParam = Annotated[
    str,
    Path(
        min_length=1,
        max_length=100,
        pattern=NAME_PATTERN,
        description="Artifact name (Q-29): letters, digits, `.`, `-`, `_`; first not punctuation.",
    ),
]


@dataclass
class UploadBody:
    file: IO[bytes]
    size: int
    sha256: str


def _too_large() -> ApiError:
    return ApiError(413, "payload_too_large", TOO_LARGE)


async def read_upload(request: Request) -> AsyncIterator[UploadBody]:
    """Read the body in chunks, stop as soon as the limit is passed (413 before any validation)."""
    declared = request.headers.get("content-length")
    if declared is not None and declared.isascii() and declared.isdigit():
        if int(declared) > MAX_UPLOAD_BYTES:
            raise _too_large()
    digest = hashlib.sha256()
    size = 0
    spool = tempfile.SpooledTemporaryFile(max_size=SPOOL_MEMORY_BYTES)  # noqa: SIM115
    try:
        async for chunk in request.stream():
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                raise _too_large()
            digest.update(chunk)
            spool.write(chunk)
        spool.seek(0)
        yield UploadBody(file=spool, size=size, sha256=digest.hexdigest())
    finally:
        spool.close()


def _repo(request: Request) -> ArtifactRepo:
    repo: ArtifactRepo = request.app.state.repo
    return repo


def _sender(request: Request) -> EventSender:
    sender: EventSender = request.app.state.sender
    return sender


@router.post(
    "/artifacts/{name}",
    operation_id="uploadArtifact",
    status_code=201,
    response_model=Artifact,
    responses={
        201: {"description": "Stored; the new version's metadata."},
        413: {"description": "The body is larger than 100 MiB (payload_too_large)."},
        422: {"description": "validation_failed, or checksum_mismatch."},
    },
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
            },
        }
    },
)
def upload_artifact(
    name: NameParam,
    build_id: Annotated[
        str,
        Query(
            pattern=UUID_PATTERN,
            json_schema_extra={"format": "uuid"},
            description="The run that produced the artifact; recorded as sent.",
        ),
    ],
    body: Annotated[UploadBody, Depends(read_upload)],
    background: BackgroundTasks,
    repo: Annotated[ArtifactRepo, Depends(_repo)],
    sender: Annotated[EventSender, Depends(_sender)],
    x_checksum_sha256: Annotated[
        str | None,
        Header(alias="X-Checksum-SHA256", pattern=CHECKSUM_PATTERN),
    ] = None,
) -> Artifact:
    if x_checksum_sha256 is not None and x_checksum_sha256 != body.sha256:
        raise ApiError(422, "checksum_mismatch", "sent checksum does not match the uploaded bytes")
    artifact = repo.create(name, build_id, body.sha256, body.size, body.file)  # committed here
    background.add_task(sender.send_uploaded, artifact)
    return artifact


@router.get(
    "/artifacts/{name}/versions/{version}",
    operation_id="downloadArtifact",
    response_class=Response,
    responses={
        200: {
            "description": "The stored bytes, with their checksum in `X-Checksum-SHA256`.",
            "content": {"application/octet-stream": {}},
        },
        404: {"description": "No artifact with this name and version (not_found)."},
        422: {"description": "The request is invalid (validation_failed)."},
    },
)
def download_artifact(
    name: NameParam,
    version: Annotated[int, Path(ge=1)],
    repo: Annotated[ArtifactRepo, Depends(_repo)],
) -> Response:
    found = repo.find(name, version)
    if found is None:
        raise ApiError(404, "not_found", f"artifact {name} version {version} not found")
    artifact, path = found
    if not path.is_file():
        raise RuntimeError("blob file is missing")  # answered as 500 internal_error
    return FileResponse(
        path,
        media_type="application/octet-stream",
        headers={"X-Checksum-SHA256": artifact.checksum},
    )

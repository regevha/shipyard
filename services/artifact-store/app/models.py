"""Pydantic models of the artifact-store (the Artifact of events.yml)."""

from datetime import UTC, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_serializer

NAME_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$"
CHECKSUM_PATTERN = r"^[0-9a-f]{64}$"
UUID_PATTERN = r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$"


class Artifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=100, pattern=NAME_PATTERN)]
    version: Annotated[int, Field(ge=1)]
    checksum: Annotated[str, Field(pattern=CHECKSUM_PATTERN)]
    size_bytes: Annotated[int, Field(ge=0, le=104_857_600)]
    build_id: Annotated[str, Field(json_schema_extra={"format": "uuid"})]
    uploaded_at: datetime

    @field_serializer("uploaded_at")
    def _ser_uploaded_at(self, value: datetime) -> str:
        return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

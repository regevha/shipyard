"""Pydantic models of contracts/api-release-service.yml. Request bodies are strict: no coercion of
"3" or true to an integer, or of a number to a string (the OpenAPI check does not compare types
that strictly, so tests cover it)."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

# events.yml ArtifactName. Pydantic's regex engine matches `$` only at the very end of the text, so
# a trailing newline is rejected as the contract requires.
ArtifactName = Annotated[
    str,
    StringConstraints(
        strict=True, min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$"
    ),
]
ArtifactVersion = Annotated[int, Field(strict=True, ge=1)]
Actor = Annotated[str, StringConstraints(strict=True, min_length=1)]
Decision = Literal["approved", "rejected"]
ReleaseStatus = Literal["pending", "approved", "rejected"]

DECISIONS: tuple[Decision, ...] = ("approved", "rejected")


class ArtifactRef(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    name: ArtifactName
    version: ArtifactVersion


class ReleaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    artifact: ArtifactRef
    requested_by: Actor


class DecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    decision: Decision
    decided_by: Actor


class Release(BaseModel):
    """One release. Fields not known yet are present and null, never absent."""

    model_config = ConfigDict(extra="forbid")

    release_id: UUID
    artifact: ArtifactRef
    status: ReleaseStatus
    requested_by: str
    requested_at: str
    decided_by: str | None
    decided_at: str | None
    promoted_at: str | None

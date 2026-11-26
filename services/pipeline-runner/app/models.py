"""Pydantic models of contracts/api-pipeline-runner.yml (request, response and internal shapes)."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

# events.yml ArtifactName / PipelineName (#119). Pydantic's regex engine matches `$` only at the
# very end of the text, so a trailing newline is rejected as the contract requires.
PipelineName = Annotated[
    str,
    StringConstraints(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$"),
]
StepName = Annotated[str, Field(min_length=1)]

StepStatus = Literal["pending", "running", "passed", "failed", "skipped"]
RunStatus = Literal["running", "passed", "failed"]
FailureReason = Literal["artifact upload failed"]

UPLOAD_FAILED: FailureReason = "artifact upload failed"


class StepDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: StepName
    command: Annotated[str, Field(min_length=1)]


class PipelineDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: PipelineName
    steps: Annotated[list[StepDefinition], Field(min_length=1)]

    @field_validator("steps")
    @classmethod
    def _unique_step_names(cls, steps: list[StepDefinition]) -> list[StepDefinition]:
        seen: set[str] = set()
        for step in steps:
            if step.name in seen:
                raise ValueError(f"duplicate step name {step.name!r}")
            seen.add(step.name)
        return steps


class StepResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: StepName
    status: StepStatus
    started_at: str | None
    finished_at: str | None


class Run(BaseModel):
    """One run (= one build, Q-28). Nullable fields are present and null, never absent."""

    model_config = ConfigDict(extra="forbid")

    build_id: UUID
    pipeline_name: PipelineName
    status: RunStatus
    created_at: str
    finished_at: str | None
    failed_step: StepName | None
    failure_reason: FailureReason | None
    steps: Annotated[list[StepResult], Field(min_length=1)]

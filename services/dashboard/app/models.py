"""Pydantic models: the events of contracts/events.yml and the views of api-dashboard.yml."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
_TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,9})?Z$")
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
_CHECKSUM_RE = re.compile(r"^[0-9a-f]{64}$")


def _no_newline(value: str) -> str:
    if "\n" in value:
        raise ValueError("must not contain a line break")
    return value


def _uuid(value: str) -> str:
    _no_newline(value)
    if not _UUID_RE.match(value):
        raise ValueError("must be a UUID")
    return value


def parse_timestamp(value: str) -> datetime:
    """Parse an RFC 3339 UTC timestamp with a Z suffix into a naive UTC datetime."""
    _no_newline(value)
    if not _TS_RE.match(value):
        raise ValueError("must be an RFC 3339 UTC date-time ending in Z")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("must be a valid date-time") from exc
    return parsed.astimezone(UTC).replace(tzinfo=None)


def _timestamp(value: str) -> str:
    parse_timestamp(value)
    return value


def _pattern(regex: re.Pattern[str], what: str) -> AfterValidator:
    def check(value: str) -> str:
        _no_newline(value)
        if not regex.match(value):
            raise ValueError(f"must be {what}")
        return value

    return AfterValidator(check)


Uuid = Annotated[str, AfterValidator(_uuid), Field(json_schema_extra={"format": "uuid"})]
Timestamp = Annotated[
    str, AfterValidator(_timestamp), Field(json_schema_extra={"format": "date-time"})
]
Name = Annotated[
    str,
    Field(min_length=1, max_length=100),
    _pattern(_NAME_RE, "letters, digits, '.', '-' or '_', starting with a letter or digit"),
]
StepName = Annotated[str, Field(min_length=1)]
Actor = Annotated[str, Field(min_length=1)]
Checksum = Annotated[str, _pattern(_CHECKSUM_RE, "64 lowercase hex characters")]
Version = Annotated[int, Field(ge=1)]
FailureReason = Literal["artifact upload failed"]
StepStatus = Literal["pending", "running", "passed", "failed", "skipped"]
BuildStatus = Literal["running", "passed", "failed"]
ReleaseStatus = Literal["pending", "approved", "rejected"]
Decision = Literal["approved", "rejected"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StepResult(Strict):
    name: StepName
    status: StepStatus
    started_at: Timestamp | None
    finished_at: Timestamp | None

    @model_validator(mode="after")
    def _state_table(self) -> StepResult:
        if self.status in ("pending", "skipped"):
            ok = self.started_at is None and self.finished_at is None
        elif self.status == "running":
            ok = self.started_at is not None and self.finished_at is None
        else:
            ok = self.started_at is not None and self.finished_at is not None
        if not ok:
            raise ValueError(f"timestamps do not fit step status {self.status}")
        return self


class ArtifactRef(Strict):
    name: Name
    version: Version


class Artifact(Strict):
    name: Name
    version: Version
    checksum: Checksum
    size_bytes: Annotated[int, Field(ge=0, le=104857600)]
    build_id: Uuid
    uploaded_at: Timestamp


class BuildStartedData(Strict):
    build_id: Uuid
    pipeline_name: Name


class BuildFinishedData(Strict):
    build_id: Uuid
    pipeline_name: Name
    outcome: Literal["passed", "failed"]
    steps: Annotated[list[StepResult], Field(min_length=1)]
    failed_step: StepName | None
    failure_reason: FailureReason | None

    @model_validator(mode="after")
    def _state_table(self) -> BuildFinishedData:
        statuses = [s.status for s in self.steps]
        if self.outcome == "passed" or self.failure_reason is not None:
            if self.failed_step is not None:
                raise ValueError("failed_step must be null")
            if any(s != "passed" for s in statuses):
                raise ValueError("every step must have passed")
            if (self.outcome == "passed") == (self.failure_reason is not None):
                raise ValueError("failure_reason is set exactly when the upload failed")
            return self
        if self.failed_step is None:
            raise ValueError("failed_step is required when a step failed")
        if statuses.count("failed") != 1 or any(
            s not in ("passed", "failed", "skipped") for s in statuses
        ):
            raise ValueError("exactly one step must have failed, the others passed or skipped")
        index = statuses.index("failed")
        if self.steps[index].name != self.failed_step:
            raise ValueError("failed_step must be the name of the failed step")
        if any(s != "passed" for s in statuses[:index]) or any(
            s != "skipped" for s in statuses[index + 1 :]
        ):
            raise ValueError("steps before the failed one passed, steps after it are skipped")
        return self


class ReleaseRequestedData(Strict):
    release_id: Uuid
    artifact: ArtifactRef
    requested_by: Actor
    requested_at: Timestamp


class ReleaseDecidedData(Strict):
    release_id: Uuid
    artifact: ArtifactRef
    decision: Decision
    decided_by: Actor
    decided_at: Timestamp


class EventBase(Strict):
    event_id: Uuid
    schema_version: Literal[1]
    occurred_at: Timestamp


class BuildStarted(EventBase):
    type: Literal["build.started"]
    source: Literal["pipeline-runner"]
    data: BuildStartedData


class BuildFinished(EventBase):
    type: Literal["build.finished"]
    source: Literal["pipeline-runner"]
    data: BuildFinishedData


class ArtifactUploaded(EventBase):
    type: Literal["artifact.uploaded"]
    source: Literal["artifact-store"]
    data: Artifact


class ReleaseRequested(EventBase):
    type: Literal["release.requested"]
    source: Literal["release-service"]
    data: ReleaseRequestedData


class ReleaseDecided(EventBase):
    type: Literal["release.decided"]
    source: Literal["release-service"]
    data: ReleaseDecidedData


Event = Annotated[
    BuildStarted | BuildFinished | ArtifactUploaded | ReleaseRequested | ReleaseDecided,
    Field(discriminator="type"),
]


class BuildView(Strict):
    build_id: Uuid
    pipeline_name: Name
    status: BuildStatus
    started_at: Timestamp | None
    finished_at: Timestamp | None
    failed_step: StepName | None
    failure_reason: FailureReason | None
    steps: list[StepResult]


class ReleaseView(Strict):
    release_id: Uuid
    artifact: ArtifactRef
    status: ReleaseStatus
    requested_by: Actor | None
    requested_at: Timestamp | None
    decided_by: Actor | None
    decided_at: Timestamp | None


class BuildPage(Strict):
    items: list[BuildView]
    limit: Annotated[int, Field(ge=1, le=200)]
    offset: Annotated[int, Field(ge=0)]


class ArtifactPage(Strict):
    items: list[Artifact]
    limit: Annotated[int, Field(ge=1, le=200)]
    offset: Annotated[int, Field(ge=0)]


class ReleasePage(Strict):
    items: list[ReleaseView]
    limit: Annotated[int, Field(ge=1, le=200)]
    offset: Annotated[int, Field(ge=0)]

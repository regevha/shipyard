"""All SQL for runs. Every method opens its own session and commits before it returns."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.models import (
    FailureReason,
    PipelineDefinition,
    Run,
    RunStatus,
    StepResult,
    StepStatus,
)
from app.repos.tables import RunRow, StepRow


def _to_run(row: RunRow, steps: list[StepRow]) -> Run:
    return Run(
        build_id=UUID(row.build_id),
        pipeline_name=row.pipeline_name,
        status=row.status,  # type: ignore[arg-type]
        created_at=row.created_at,
        finished_at=row.finished_at,
        failed_step=row.failed_step,
        failure_reason=row.failure_reason,  # type: ignore[arg-type]
        steps=[
            StepResult(
                name=s.name,
                status=s.status,  # type: ignore[arg-type]
                started_at=s.started_at,
                finished_at=s.finished_at,
            )
            for s in steps
        ],
    )


class RunRepo:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def create(self, build_id: UUID, definition: PipelineDefinition, now: str) -> Run:
        with self._factory() as session:
            row = RunRow(
                build_id=str(build_id),
                pipeline_name=definition.name,
                status="running",
                created_at=now,
            )
            session.add(row)
            steps = [
                StepRow(
                    build_id=str(build_id),
                    position=i,
                    name=step.name,
                    command=step.command,
                    status="pending",
                )
                for i, step in enumerate(definition.steps)
            ]
            session.add_all(steps)
            session.commit()
            return _to_run(row, steps)

    def get(self, build_id: UUID) -> Run | None:
        with self._factory() as session:
            row = session.get(RunRow, str(build_id))
            if row is None:
                return None
            return _to_run(row, self._steps(session, build_id))

    def count(self) -> int:
        with self._factory() as session:
            return session.scalar(select(func.count()).select_from(RunRow)) or 0

    def commands(self, build_id: UUID) -> list[str]:
        with self._factory() as session:
            return [s.command for s in self._steps(session, build_id)]

    @staticmethod
    def _steps(session: Session, build_id: UUID) -> list[StepRow]:
        stmt = select(StepRow).where(StepRow.build_id == str(build_id)).order_by(StepRow.position)
        return list(session.scalars(stmt))

    def set_step(
        self,
        build_id: UUID,
        position: int,
        status: StepStatus,
        started_at: str | None = None,
        finished_at: str | None = None,
    ) -> None:
        with self._factory() as session:
            step = session.get(StepRow, (str(build_id), position))
            assert step is not None
            step.status = status
            if started_at is not None:
                step.started_at = started_at
            if finished_at is not None:
                step.finished_at = finished_at
            session.commit()

    def skip_steps_from(self, build_id: UUID, position: int) -> None:
        with self._factory() as session:
            for step in self._steps(session, build_id):
                if step.position >= position:
                    step.status = "skipped"
            session.commit()

    def finish(
        self,
        build_id: UUID,
        status: RunStatus,
        finished_at: str,
        failed_step: str | None = None,
        failure_reason: FailureReason | None = None,
    ) -> Run:
        with self._factory() as session:
            row = session.get(RunRow, str(build_id))
            assert row is not None
            row.status = status
            row.finished_at = finished_at
            row.failed_step = failed_step
            row.failure_reason = failure_reason
            session.commit()
            return _to_run(row, self._steps(session, build_id))

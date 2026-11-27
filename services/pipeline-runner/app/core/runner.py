"""Simulated pipeline execution. Commands are never executed (Q-19): exactly "fail" fails a step
(Q-33). One fake upload when every step passed, before the run is marked passed (Q-34, Q-36)."""

from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Callable
from uuid import UUID

import httpx

from app.core.config import Settings
from app.core.events import EventSender
from app.core.timeutil import now_iso
from app.models import UPLOAD_FAILED, Run
from app.repos.runs import RunRepo

log = logging.getLogger("pipeline-runner.runner")

FAIL_COMMAND = "fail"


class Runner:
    def __init__(
        self,
        repo: RunRepo,
        events: EventSender,
        settings: Settings,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._repo = repo
        self._events = events
        self._settings = settings
        self._transport = transport
        self._sleep = sleep

    def execute(self, build_id: UUID) -> None:
        """Run in the background; never raises."""
        try:
            self._execute(build_id)
        except Exception:
            log.exception("run %s aborted by an unexpected error", build_id)
            self._fail_internal(build_id)

    def _fail_internal(self, build_id: UUID) -> None:
        """Q-41: mark the run failed with `internal error` and send build.finished. A run whose
        final state is already committed keeps it. Never raises."""
        try:
            done = self._repo.fail_internal(build_id, now_iso())
            if done is not None:
                self._events.build_finished(done)
        except Exception:
            log.exception("run %s could not be marked failed", build_id)

    def _execute(self, build_id: UUID) -> None:
        run = self._repo.get(build_id)
        assert run is not None
        commands = self._repo.commands(build_id)
        for position, command in enumerate(commands):
            started = now_iso()
            self._repo.set_step(build_id, position, "running", started_at=started)
            if position == 0:
                self._events.build_started(run, started)
            if self._settings.step_seconds > 0:
                self._sleep(self._settings.step_seconds)
            finished = now_iso()
            if command == FAIL_COMMAND:
                done = self._repo.fail_step(build_id, position, finished)
                self._events.build_finished(done)
                return
            self._repo.set_step(build_id, position, "passed", finished_at=finished)
        # Every step passed: one upload attempt while the run is still "running" (Q-36).
        if self._upload(run):
            done = self._repo.finish(build_id, "passed", now_iso())
        else:
            done = self._repo.finish(build_id, "failed", now_iso(), failure_reason=UPLOAD_FAILED)
        self._events.build_finished(done)

    def _upload(self, run: Run) -> bool:
        """One attempt, no retry. True only on 201."""
        s = self._settings
        body = f"fake artifact of build {run.build_id}\n".encode()
        url = f"{s.artifact_store_url.rstrip('/')}/artifacts/{run.pipeline_name}"
        try:
            with httpx.Client(
                transport=self._transport, timeout=s.upload_timeout_seconds
            ) as client:
                response = client.post(
                    url,
                    params={"build_id": str(run.build_id)},
                    content=body,
                    headers={
                        "Content-Type": "application/octet-stream",
                        "X-Checksum-SHA256": hashlib.sha256(body).hexdigest(),
                    },
                )
        except httpx.HTTPError as exc:  # network error or timeout: the upload failed
            log.warning("artifact upload of build %s failed: %s", run.build_id, type(exc).__name__)
            return False
        if response.status_code != 201:
            log.warning(
                "artifact upload of build %s answered %d", run.build_id, response.status_code
            )
            return False
        return True

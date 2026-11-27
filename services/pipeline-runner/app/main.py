from __future__ import annotations

import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from app.core.config import Settings
from app.core.events import EventSender
from app.core.runner import Runner
from app.errors import install
from app.repos.engine import init_db, make_engine
from app.repos.runs import RunRepo
from app.routers import runs


def create_app(
    settings: Settings | None = None,
    transport: httpx.BaseTransport | None = None,
    sleep: Callable[[float], None] = time.sleep,
    events: EventSender | None = None,
) -> FastAPI:
    """Settings default to the environment, read at startup. `transport` (the upload) and
    `events` (the event sender, async) let tests fake the other services (httpx.MockTransport);
    `sleep` replaces the simulated step delay."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        cfg = settings or Settings.from_env()
        engine = make_engine(cfg.database_url)
        repo = RunRepo(init_db(engine))
        sender = events or EventSender(cfg.dashboard_url)
        await sender.start()  # binds to the server's event loop
        app.state.events = sender
        app.state.settings = cfg
        app.state.repo = repo
        app.state.runner = Runner(repo, sender, cfg, transport, sleep)
        try:
            yield
        finally:
            await sender.close()
            engine.dispose()

    app = FastAPI(title="pipeline-runner", version="0.1.0", lifespan=lifespan)
    app.include_router(runs.router)
    install(app)
    return app


app = create_app()

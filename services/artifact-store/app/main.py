from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import Settings
from app.core.events import EventSender
from app.errors import install
from app.repos.artifacts import ArtifactRepo
from app.repos.blobs import BlobStore
from app.repos.engine import make_engine
from app.routers import artifacts


def create_app(settings: Settings | None = None, sender: EventSender | None = None) -> FastAPI:
    """Build the app; tests pass their own settings (tmp dir, memory database) and sender."""
    cfg = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = make_engine(cfg.database_url)
        cfg.data_dir.mkdir(parents=True, exist_ok=True)
        repo = ArtifactRepo(engine, BlobStore(cfg.blob_dir))
        repo.create_tables()
        app.state.repo = repo
        events = sender or EventSender(cfg.dashboard_url)
        await events.start()
        app.state.sender = events
        try:
            yield
        finally:
            await events.close()
            engine.dispose()

    application = FastAPI(title="artifact-store", version="0.1.0", lifespan=lifespan)
    application.include_router(artifacts.router)
    install(application)
    return application


app = create_app()

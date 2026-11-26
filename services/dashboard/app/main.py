from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.errors import install
from app.repos.engine import get_engine, init_db
from app.routers import events, views

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    init_db(get_engine())
    yield


app = FastAPI(title="dashboard", version="0.1.0", lifespan=lifespan)
app.include_router(events.router)
app.include_router(views.router)


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html", media_type="text/html")


# Not mounted at "/": a catch-all mount would break the 404/405 rule of contracts/errors.yml.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
install(app)

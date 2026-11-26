"""Database engine, the only place that reads the URL and knows about SQLite."""

import os
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.repos.tables import Base


def database_url() -> str:
    url = os.environ.get("DASHBOARD_DATABASE_URL")
    if url:
        return url
    slot = os.environ.get("SHIPYARD_SLOT", "0")
    data_dir = os.environ.get("SHIPYARD_DATA_DIR", f"/tmp/shipyard/slot{slot}")
    return f"sqlite:///{data_dir}/dashboard.db"


def make_engine(url: str) -> Engine:
    if not url.startswith("sqlite"):
        return create_engine(url)
    kwargs: dict[str, Any] = {"connect_args": {"check_same_thread": False}}
    if url in ("sqlite://", "sqlite:///:memory:"):
        kwargs["poolclass"] = StaticPool
    elif url.startswith("sqlite:///"):
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, **kwargs)

    @event.listens_for(engine, "connect")
    def _foreign_keys(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def init_db(engine: Engine) -> None:
    """Create the tables (idempotent); wave 2 has no migrations."""
    Base.metadata.create_all(engine)


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return make_engine(database_url())


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session per request. Writes commit inside the repo function."""
    with sessionmaker(get_engine(), expire_on_commit=False)() as session:
        yield session

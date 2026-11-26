"""Engine and session factory; the only place that knows about SQLite (foreign-key pragma)."""

from __future__ import annotations

import os
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.repos.tables import Base


def make_engine(url: str) -> Engine:
    parsed = make_url(url)
    if parsed.get_backend_name() != "sqlite":
        return create_engine(url)
    # timeout = busy timeout (s): a writer waits for the lock instead of failing at once.
    # isolation_level=None hands transaction start to the "begin" hook below (BEGIN IMMEDIATE).
    kwargs: dict[str, Any] = {
        "connect_args": {"check_same_thread": False, "timeout": 60, "isolation_level": None}
    }
    if parsed.database in (None, "", ":memory:"):
        kwargs["poolclass"] = StaticPool
    elif not parsed.database.startswith("file:"):
        os.makedirs(os.path.dirname(os.path.abspath(parsed.database)), exist_ok=True)
    engine = create_engine(url, **kwargs)

    @event.listens_for(engine, "connect")
    def _foreign_keys(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        if parsed.database not in (None, "", ":memory:"):
            cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    @event.listens_for(engine, "begin")
    def _begin_immediate(connection: Any) -> None:
        # Take the write lock up front: a read-then-write transaction that starts deferred cannot
        # upgrade under contention and fails with "database is locked" regardless of the timeout.
        connection.exec_driver_sql("BEGIN IMMEDIATE")

    return engine


def init_db(engine: Engine) -> sessionmaker[Session]:
    """Create the tables (idempotent) and return the session factory."""
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)

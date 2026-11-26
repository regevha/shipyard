"""SQLite engine: file DBs use WAL, a 60 s busy timeout and BEGIN IMMEDIATE."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text

from app.repos.engine import make_engine


def test_file_db_uses_wal_busy_timeout_and_foreign_keys(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path}/sub/x.db")
    with engine.connect() as conn:
        assert conn.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
        assert conn.exec_driver_sql("PRAGMA busy_timeout").scalar() == 60000
        assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
        conn.execute(text("SELECT 1"))
    engine.dispose()


def test_memory_db_is_shared_across_connections() -> None:
    engine = make_engine("sqlite://")
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE t (x INTEGER)")
    with engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT count(*) FROM t").scalar() == 0
    engine.dispose()

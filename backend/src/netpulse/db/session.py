"""Engine + session factory. SQLite in WAL mode, tables created on first use.

The store is a single append-only SQLite file. WAL lets the API read while the collector
writes. Schema is small and stable, so tables are created from metadata on startup;
Alembic (a declared dep) is reserved for a future breaking change.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from netpulse.db import models  # noqa: F401  (registers tables on Base.metadata)
from netpulse.db.base import Base
from netpulse.db.migrate import ensure_indexes, ensure_network_columns

_engine: Engine | None = None
_Session: sessionmaker[Session] | None = None


def _configure_sqlite(dbapi_conn: object, _record: object) -> None:
    cur = dbapi_conn.cursor()  # type: ignore[attr-defined]
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.execute("PRAGMA busy_timeout=5000")
    cur.close()


def init_engine(db_path: Path) -> Engine:
    global _engine, _Session  # noqa: PLW0603 — process-wide engine singleton
    db_path.parent.mkdir(parents=True, exist_ok=True)
    _engine = create_engine(f"sqlite:///{db_path}", future=True)
    event.listen(_engine, "connect", _configure_sqlite)
    Base.metadata.create_all(_engine)
    ensure_network_columns(_engine)
    ensure_indexes(_engine)
    _Session = sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_session() -> Session:
    if _Session is None:
        raise RuntimeError("engine not initialized — call init_engine() first")
    return _Session()

"""Lightweight pre-Alembic migrations.

``create_all`` creates new tables but never alters existing ones, so when a column is added to
a model an existing DB needs the column backfilled by hand. This adds ``network_id`` to the
sample tables if it is missing (idempotent). Alembic (C1 on the roadmap) will replace this.
"""

from __future__ import annotations

from sqlalchemy import Engine, text

from netpulse.db.base import Base
from netpulse.db.models import NetworkScoped

# Derived from the mapped models so it can never drift from the schema (audit M3): every table
# whose model inherits NetworkScoped must carry a network_id column on an upgraded DB.
_NETWORK_SCOPED_TABLES = tuple(
    m.__tablename__  # type: ignore[attr-defined]  # every subclass is a mapped model with a table
    for m in NetworkScoped.__subclasses__()
)


def _columns(conn: object, table: str) -> set[str]:
    rows = conn.execute(text(f"PRAGMA table_info({table})")).all()  # type: ignore[attr-defined]
    return {r[1] for r in rows}


# Columns added to existing tables after their initial ship (table, column, SQL type, index?).
_ADDED_COLUMNS: tuple[tuple[str, str, str, bool], ...] = (
    *((t, "network_id", "INTEGER", True) for t in _NETWORK_SCOPED_TABLES),
    ("wifi_raw", "tx_packets", "INTEGER", False),
    ("wifi_raw", "power_save", "BOOLEAN", False),
    ("ping_raw", "af", "TEXT", False),
)


def ensure_indexes(engine: Engine) -> None:
    """Create any declared index that a pre-existing DB lacks — `create_all` only indexes tables it
    creates, so composite indexes added after ship must be applied here (idempotent)."""
    with engine.begin() as conn:
        for table in Base.metadata.tables.values():
            for index in table.indexes:
                index.create(bind=conn, checkfirst=True)


def ensure_network_columns(engine: Engine) -> None:
    with engine.begin() as conn:
        rows = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        existing = {r[0] for r in rows}
        for table, column, sql_type, indexed in _ADDED_COLUMNS:
            if table not in existing or column in _columns(conn, table):
                continue
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}"))
            if indexed:
                conn.execute(
                    text(f"CREATE INDEX IF NOT EXISTS ix_{table}_{column} ON {table}({column})")
                )

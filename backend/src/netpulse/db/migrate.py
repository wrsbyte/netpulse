"""Lightweight pre-Alembic migrations.

``create_all`` creates new tables but never alters existing ones, so when a column is added to
a model an existing DB needs the column backfilled by hand. This adds ``network_id`` to the
sample tables if it is missing (idempotent). Alembic (C1 on the roadmap) will replace this.
"""

from __future__ import annotations

from sqlalchemy import Engine, text

_NETWORK_SCOPED_TABLES = (
    "ping_raw", "wifi_raw", "throughput_raw", "dns_raw", "agg",
    "active_test", "traceroute", "flow", "wifi_scan", "event",
)


def _columns(conn: object, table: str) -> set[str]:
    rows = conn.execute(text(f"PRAGMA table_info({table})")).all()  # type: ignore[attr-defined]
    return {r[1] for r in rows}


# Columns added to existing tables after their initial ship (table, column, SQL type, index?).
_ADDED_COLUMNS: tuple[tuple[str, str, str, bool], ...] = (
    *((t, "network_id", "INTEGER", True) for t in _NETWORK_SCOPED_TABLES),
    ("wifi_raw", "tx_packets", "INTEGER", False),
    ("wifi_raw", "power_save", "BOOLEAN", False),
)


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

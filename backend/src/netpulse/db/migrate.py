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


def ensure_network_columns(engine: Engine) -> None:
    with engine.begin() as conn:
        rows = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        existing = {r[0] for r in rows}
        for table in _NETWORK_SCOPED_TABLES:
            if table not in existing or "network_id" in _columns(conn, table):
                continue
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN network_id INTEGER"))
            conn.execute(
                text(f"CREATE INDEX IF NOT EXISTS ix_{table}_network_id ON {table}(network_id)")
            )

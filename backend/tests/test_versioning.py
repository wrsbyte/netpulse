"""Data provenance: every sample carries the code version that produced it (DATA_VERSIONING.md)."""

import time
from pathlib import Path

from sqlalchemy import create_engine, text

from netpulse import __version__
from netpulse.db.migrate import ensure_network_columns
from netpulse.db.models import PingRaw
from netpulse.db.session import get_session, init_engine


def test_new_sample_is_stamped_with_running_version(tmp_path: Path) -> None:
    # A row inserted by the running process defaults to that process's version — no per-call wiring.
    init_engine(tmp_path / "v.db")
    with get_session() as s:
        s.add(PingRaw(ts=time.time(), target="1.1.1.1", loss_pct=0.0, rtt_avg=10.0))
        s.commit()
    with get_session() as s:
        row = s.query(PingRaw).one()
    assert __version__ != "0.0.0"  # the sentinel must never be the running version
    assert row.code_version == __version__


def test_migration_adds_code_version_and_backfills_untrusted_sentinel(tmp_path: Path) -> None:
    # A pre-versioning DB (table without the column) must gain code_version, and its existing rows
    # must backfill to "0.0.0" — provenance unknown, not silently attributed to the current version.
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as c:
        c.execute(text("CREATE TABLE ping_raw (id INTEGER PRIMARY KEY, ts FLOAT, target TEXT)"))
        c.execute(text("INSERT INTO ping_raw (ts, target) VALUES (1.0, 'x')"))
    ensure_network_columns(engine)
    with engine.begin() as c:
        cols = {r[1] for r in c.execute(text("PRAGMA table_info(ping_raw)"))}
        assert "code_version" in cols
        assert c.execute(text("SELECT code_version FROM ping_raw")).scalar() == "0.0.0"

import time
from pathlib import Path

from sqlalchemy import func, select

from netpulse.aggregation import run_rollups
from netpulse.config import Retention
from netpulse.db.models import Agg, PingRaw
from netpulse.db.session import get_session, init_engine


def _seed_pings(tmp_path: Path) -> float:
    init_engine(tmp_path / "agg.db")
    now = time.time()
    with get_session() as s:
        for i in range(10):
            s.add(PingRaw(ts=now - i * 10, target="1.1.1.1", loss_pct=0.0, rtt_avg=50.0 + i))
        s.commit()
    return now


def test_rollup_is_idempotent(tmp_path: Path) -> None:
    # Running the rollup twice over the same window must not duplicate Agg rows (delete+insert).
    now = _seed_pings(tmp_path)
    with get_session() as s:
        run_rollups(s, Retention(), now)
    with get_session() as s:
        first = s.scalar(select(func.count()).select_from(Agg))
        run_rollups(s, Retention(), now)
        second = s.scalar(select(func.count()).select_from(Agg))
    assert first == second
    assert first and first > 0


def test_rollup_computes_5m_and_1h_for_rtt(tmp_path: Path) -> None:
    now = _seed_pings(tmp_path)
    with get_session() as s:
        run_rollups(s, Retention(), now)
        rows = s.scalars(
            select(Agg).where(Agg.metric == "ping.rtt_avg", Agg.tag == "1.1.1.1")
        ).all()
    resolutions = {r.resolution for r in rows}
    assert resolutions == {"5m", "1h"}
    five = next(r for r in rows if r.resolution == "5m")
    assert five.n == 10
    assert five.mn == 50.0 and five.mx == 59.0

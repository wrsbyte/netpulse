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


def test_1h_rollup_preserves_the_tail_not_mean_of_means(tmp_path: Path) -> None:
    # Spread samples over several 5-min buckets within one hour, with one big spike. The 1h
    # aggregate must keep the spike (max/p95) and count real samples, not collapse to a
    # p95-of-5min-averages that smooths the tail away.
    init_engine(tmp_path / "agg1h.db")
    now = time.time()
    with get_session() as s:
        for i in range(30):  # ~29 min span -> multiple 5-min buckets
            rtt = 300.0 if i == 5 else 50.0
            s.add(PingRaw(ts=now - i * 60, target="1.1.1.1", loss_pct=0.0, rtt_avg=rtt))
        s.commit()
    with get_session() as s:
        run_rollups(s, Retention(), now)
        one_h = s.scalars(
            select(Agg).where(
                Agg.resolution == "1h", Agg.metric == "ping.rtt_avg", Agg.tag == "1.1.1.1"
            )
        ).all()
    total_n = sum(a.n for a in one_h)
    assert total_n == 30  # real sample count, not the number of 5-min buckets
    assert max(a.mx for a in one_h if a.mx is not None) == 300.0  # spike survives
    # p95 surfaces the tail (well above the ~90 a p95-of-5min-averages would report).
    assert max(a.p95 for a in one_h if a.p95 is not None) > 150.0


def test_rollup_computes_5m_and_1h_for_rtt(tmp_path: Path) -> None:
    now = _seed_pings(tmp_path)
    with get_session() as s:
        run_rollups(s, Retention(), now)
        rows = s.scalars(
            select(Agg).where(Agg.metric == "ping.rtt_avg", Agg.tag == "1.1.1.1")
        ).all()
    resolutions = {r.resolution for r in rows}
    assert resolutions == {"5m", "1h"}
    # The 10 samples may straddle a 5-min boundary; assert over all 5m rows, not one bucket.
    five = [r for r in rows if r.resolution == "5m"]
    assert sum(r.n for r in five) == 10
    assert min(r.mn for r in five if r.mn is not None) == 50.0
    assert max(r.mx for r in five if r.mx is not None) == 59.0

import time
from pathlib import Path

from netpulse.analysis.verdict import conclude
from netpulse.api import queries
from netpulse.db.models import PingRaw
from netpulse.db.session import get_session, init_engine


def _ping(ts: float, target: str, rtt: float, loss: float = 0.0) -> PingRaw:
    return PingRaw(ts=ts, target=target, loss_pct=loss, rtt_avg=rtt, rtt_min=rtt - 1, jitter=1.0)


def test_latency_is_per_target_not_pooled(tmp_path: Path) -> None:
    # A distant-but-healthy work host (150 ms) must NOT drag "internet latency" up: the two nearby
    # resolvers (15/18 ms) make the representative latency ~18 ms, not the pooled ~150 ms tail.
    init_engine(tmp_path / "gs.db")
    now = time.time()
    with get_session() as s:
        for i in range(30):
            t = now - i * 3
            s.add_all([
                _ping(t, "8.8.8.8", 15.0),
                _ping(t, "9.9.9.9", 18.0),
                _ping(t, "131.153.11.143", 150.0),  # distant work host
            ])
        s.commit()
    with get_session() as s:
        stats = queries.gather_stats(s, window=6 * 3600, window_label="", network_id=None)
    assert stats.latency is not None and stats.latency < 50  # representative, not the 150 ms tail
    assert stats.latency_excess is not None and stats.latency_excess < 10  # per-target floor


def test_grade_loss_is_average_not_p95_of_quantized_loss(tmp_path: Path) -> None:
    # A target clean on average but with occasional full-drop cycles must be graded on its ~2%
    # AVERAGE loss, not a p95 that quantizes to ~33% and slams the grade to F.
    init_engine(tmp_path / "gs2.db")
    now = time.time()
    with get_session() as s:
        for i in range(60):
            t = now - i * 3
            loss = 33.3 if i % 30 == 0 else 0.0  # ~3% of cycles drop
            s.add(_ping(t, "8.8.8.8", 16.0, loss=loss))
            s.add(_ping(t, "9.9.9.9", 18.0))
        s.commit()
    with get_session() as s:
        stats = queries.gather_stats(s, window=6 * 3600, window_label="", network_id=None)
    assert stats.loss is not None and stats.loss < 5  # the average, not the ~33% p95
    assert conclude(stats).score.grade != "F"

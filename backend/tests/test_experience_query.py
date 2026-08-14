import time
from pathlib import Path

from netpulse.api import queries
from netpulse.db.models import MediaRaw, PingRaw
from netpulse.db.session import get_session, init_engine


def _clean_pings(s, now: float) -> None:
    for i in range(30):
        s.add(PingRaw(ts=now - i * 3, target="8.8.8.8", loss_pct=0.0, rtt_avg=18.0, rtt_min=17.0,
                      jitter=1.0))


def test_experience_uses_live_media_for_calls(tmp_path: Path) -> None:
    init_engine(tmp_path / "expq.db")
    now = time.time()
    with get_session() as s:
        _clean_pings(s, now)
        s.add(MediaRaw(ts=now - 10, remote_ip="1.2.3.4", app="Meet", endpoints=2,
                       rtt_ms=40.0, loss_pct=0.0, jitter_ms=6.0))
        s.commit()
    with get_session() as s:
        out = queries.experience(s, window=6 * 3600, network_id=None)
    calls = next(a for a in out.activities if a.activity == "Video calls")
    assert calls.rating == "good"
    assert "Meet" in calls.summary
    assert any("live" in m.label for m in calls.metrics)


def test_experience_ignores_stale_media(tmp_path: Path) -> None:
    init_engine(tmp_path / "expq2.db")
    now = time.time()
    with get_session() as s:
        _clean_pings(s, now)
        # media older than 120 s must not drive the call rating (no active call)
        s.add(MediaRaw(ts=now - 300, remote_ip="1.2.3.4", app="Meet", endpoints=2,
                       rtt_ms=40.0, loss_pct=0.0, jitter_ms=99.0))
        s.commit()
    with get_session() as s:
        out = queries.experience(s, window=6 * 3600, network_id=None)
    calls = next(a for a in out.activities if a.activity == "Video calls")
    assert not any("live" in m.label for m in calls.metrics)  # fell back to proxies

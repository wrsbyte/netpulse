import time
from pathlib import Path

from netpulse.api import queries
from netpulse.db.models import PingRaw, ThroughputRaw
from netpulse.db.session import get_session, init_engine


def test_status_uses_fresh_raw_before_any_rollup(tmp_path: Path) -> None:
    # Right after boot only raw samples exist (no Agg yet); status must still report
    # current latency / online from them — the bug was reading from the empty rollup.
    init_engine(tmp_path / "t.db")
    now = time.time()
    with get_session() as s:
        s.add_all([
            PingRaw(ts=now - 5, target="1.1.1.1", loss_pct=0.0, rtt_avg=12.0),
            PingRaw(ts=now - 5, target="8.8.8.8", loss_pct=0.0, rtt_avg=20.0),
            PingRaw(ts=now - 5, target="192.168.100.1", loss_pct=0.0, rtt_avg=2.0),
        ])
        s.commit()

    with get_session() as s:
        status = queries.status(s, window=6 * 3600, interface="wlan0")

    assert status.online is True
    assert status.current_rtt == 2.0  # best (lowest) reachable RTT
    assert status.current_loss == 0.0


def test_status_offline_when_all_targets_lost(tmp_path: Path) -> None:
    init_engine(tmp_path / "t2.db")
    now = time.time()
    with get_session() as s:
        s.add_all([
            PingRaw(ts=now - 5, target="1.1.1.1", loss_pct=100.0),
            PingRaw(ts=now - 5, target="8.8.8.8", loss_pct=100.0),
        ])
        s.commit()

    with get_session() as s:
        status = queries.status(s, window=6 * 3600, interface="wlan0")

    assert status.online is False
    assert status.current_rtt is None
    assert status.current_loss == 100.0


def test_status_surfaces_live_throughput_in_use(tmp_path: Path) -> None:
    init_engine(tmp_path / "tput.db")
    now = time.time()
    with get_session() as s:
        s.add_all([
            PingRaw(ts=now - 5, target="8.8.8.8", loss_pct=0.0, rtt_avg=18.0),
            ThroughputRaw(ts=now - 4, rx_bps=42_000_000, tx_bps=5_000_000),
        ])
        s.commit()
    with get_session() as s:
        status = queries.status(s, window=6 * 3600, interface="wlan0")
    assert status.current_rx_mbps == 42.0
    assert status.current_tx_mbps == 5.0

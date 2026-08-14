import time
from pathlib import Path

from netpulse.api import queries
from netpulse.db.models import PingRaw, WifiScan
from netpulse.db.session import get_session, init_engine


def test_ping_samples_during_a_wifi_scan_are_dropped(tmp_path: Path) -> None:
    # A WiFi scan takes the radio off-channel: the ping at that instant spikes/loses on every
    # target and must be excluded from health stats; samples away from the scan stay.
    init_engine(tmp_path / "scan.db")
    now = time.time()
    scan_t = now - 100
    with get_session() as s:
        s.add_all([
            WifiScan(ts=scan_t, channel=36, signal_dbm=-50.0, bssid="aa"),
            PingRaw(ts=scan_t, target="8.8.8.8", loss_pct=100.0, rtt_avg=200.0),  # artifact
            PingRaw(ts=scan_t + 2, target="8.8.8.8", loss_pct=20.0, rtt_avg=150.0),  # within guard
            PingRaw(ts=scan_t + 30, target="8.8.8.8", loss_pct=0.0, rtt_avg=15.0),  # clean
            PingRaw(ts=now - 5, target="8.8.8.8", loss_pct=0.0, rtt_avg=16.0),  # clean
        ])
        s.commit()
    with get_session() as s:
        pings = s.query(PingRaw).all()
        kept = queries._drop_scan_artifacts(s, pings, start=now - 3600, network_id=None)
    losses = sorted(p.loss_pct for p in kept)
    assert losses == [0.0, 0.0]  # both artifact samples (100% and 20%) removed
    assert len(kept) == 2

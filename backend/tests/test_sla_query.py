import time
from pathlib import Path

from netpulse.api import queries
from netpulse.db.models import Event, PingRaw
from netpulse.db.session import get_session, init_engine


def _pings(s, now: float) -> None:
    for i in range(40):
        s.add(PingRaw(ts=now - i * 3, target="8.8.8.8", loss_pct=0.0, rtt_avg=18.0, rtt_min=17.0))


def test_sla_uptime_ignores_local_wifi_outages(tmp_path: Path) -> None:
    init_engine(tmp_path / "slaq.db")
    now = time.time()
    with get_session() as s:
        _pings(s, now)
        # a local WiFi drop must NOT count against the ISP contract
        s.add(Event(ts=now - 60, end_ts=now - 30, kind="outage",
                    severity="error", detail="wifi/lan"))
        s.commit()
    with get_session() as s:
        report = queries.sla(s, window=7 * 86400, window_label="7d", network_id=None)
    uptime = next(line for line in report.lines if line.metric == "Uptime")
    assert uptime.measured == 100.0  # local drop ignored → no ISP breach


def test_sla_uptime_counts_isp_outages(tmp_path: Path) -> None:
    init_engine(tmp_path / "slaq2.db")
    now = time.time()
    with get_session() as s:
        _pings(s, now)
        s.add(Event(ts=now - 60, end_ts=now - 30, kind="outage", severity="error", detail="isp"))
        s.commit()
    with get_session() as s:
        report = queries.sla(s, window=7 * 86400, window_label="7d", network_id=None)
    uptime = next(line for line in report.lines if line.metric == "Uptime")
    assert uptime.measured is not None and uptime.measured < 100.0  # ISP outage does count

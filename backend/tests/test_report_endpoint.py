import time
from pathlib import Path

from netpulse.api.routers.report import get_report
from netpulse.db.models import ActiveTest, DnsRaw, Event, PingRaw
from netpulse.db.session import get_session, init_engine


def test_report_composes_sections_and_rounds_numbers(tmp_path: Path) -> None:
    init_engine(tmp_path / "report.db")
    now = time.time()
    with get_session() as s:
        for i in range(20):
            s.add_all([
                PingRaw(ts=now - i * 3, target="8.8.8.8", loss_pct=0.0, rtt_avg=18.0, rtt_min=17.0),
                PingRaw(ts=now - i * 3, target="9.9.9.9", loss_pct=0.0, rtt_avg=20.0, rtt_min=19.0),
            ])
        s.add_all([
            ActiveTest(ts=now - 60, download_mbps=195.0, upload_mbps=196.0, idle_latency=3.0),
            DnsRaw(ts=now - 10, domain="x.com", resolver="9.9.9.9", query_ms=18.0, ok=True),
            Event(ts=now - 300, end_ts=now - 282, kind="outage", severity="error",
                  detail="wifi/lan"),
        ])
        s.commit()
    with get_session() as s:
        resp = get_report(s, range="24h", network="all")
    html = resp.body.decode()
    assert "<!doctype html>" in html
    for section in ("Findings", "DNS resolvers", "Outages", "Contract vs delivered"):
        assert section in html
    assert "999999" not in html  # numbers are rounded, no float noise
    assert "Grade" in html and "the last 24 hours" in html

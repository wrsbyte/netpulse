import time
from pathlib import Path

from netpulse.api import queries
from netpulse.db.models import FlowQuality
from netpulse.db.session import get_session, init_engine


def test_flow_services_collapses_endpoints_by_service(tmp_path: Path) -> None:
    # Many raw Microsoft IPv6 endpoints must collapse into one "Microsoft" row (ASN org),
    # while classified apps keep their name — no wall of raw IPs.
    init_engine(tmp_path / "svc.db")
    now = time.time()

    def fq(ip: str, asn: str, app: str | None, mbps: float) -> FlowQuality:
        return FlowQuality(
            ts=now, remote_ip=ip, asn=asn, app=app, srtt_ms=60.0, min_rtt_ms=50.0,
            retrans_total=1, delivery_mbps=mbps, sockets=1,
        )

    with get_session() as s:
        s.add_all([
            fq("2603::1", "8075", None, 0.5),
            fq("2603::2", "8075", None, 0.3),
            fq("2603::3", "8075", None, 0.2),
            fq("142.250.1.1", "15169", "Google", 4.0),
        ])
        s.commit()

    with get_session() as s:
        svcs = queries.flow_services(s, window=3600, network_id=None)

    by = {v.service: v for v in svcs}
    assert "Microsoft" in by  # 3 AS8075 endpoints collapsed by ASN org
    assert by["Microsoft"].endpoints == 3
    assert by["Microsoft"].retrans_total == 3
    assert by["Google"].endpoints == 1
    # sorted by goodput desc -> Google (4.0) before Microsoft (1.0 summed)
    assert svcs[0].service == "Google"

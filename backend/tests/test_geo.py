import time
from pathlib import Path

from netpulse.api import queries
from netpulse.db.models import AnycastPop, HopLocation, PingRaw, Traceroute
from netpulse.db.session import get_session, init_engine


def test_geo_map_annotates_pops_with_measured_rtt_and_loss(tmp_path: Path) -> None:
    # The map must carry the RTT/loss actually measured to each destination, not just its location.
    init_engine(tmp_path / "geo.db")
    now = time.time()
    with get_session() as s:
        s.add_all([
            AnycastPop(
                ts=now - 10, provider="cloudflare", target="1.1.1.1", colo="DFW",
                colo_country="US", client_country="MX", out_of_country=True,
            ),
            # loss ~5%, rtt ~90ms to Cloudflare; a clean local gateway
            PingRaw(ts=now - 5, target="1.1.1.1", loss_pct=6.0, rtt_avg=90.0),
            PingRaw(ts=now - 4, target="1.1.1.1", loss_pct=4.0, rtt_avg=92.0),
            PingRaw(ts=now - 5, target="192.168.100.1", loss_pct=0.0, rtt_avg=2.0),
        ])
        s.commit()

    with get_session() as s:
        geo = queries.geo_map(s, network_id=None)

    pop = next(p for p in geo.points if p.kind == "pop")
    assert pop.provider == "cloudflare"
    assert pop.rtt_ms == 91.0
    assert pop.loss_pct == 5.0
    assert pop.out_of_country is True
    arc = geo.arcs[0]
    assert arc.rtt_ms == 91.0 and arc.loss_pct == 5.0
    you = next(p for p in geo.points if p.kind == "you")
    assert you.rtt_ms == 2.0  # local gateway RTT annotated on the "you" node


def test_geo_map_builds_geolocated_hop_path(tmp_path: Path) -> None:
    init_engine(tmp_path / "geopath.db")
    now = time.time()

    def tr(hop: int, host: str, rtt: float, loss: float = 0.0) -> Traceroute:
        return Traceroute(ts=now, target="1.1.1.1", hop=hop, host=host, loss_pct=loss, rtt_ms=rtt)

    with get_session() as s:
        s.add_all([
            tr(1, "10.0.0.1", 2.0),  # private -> not located
            tr(2, "201.174.1.1", 12.0),
            tr(3, "141.101.74.40", 50.0, loss=1.0),
            HopLocation(ip="201.174.1.1", ts=now, located=True, lat=20.6, lon=-103.3,
                        city="Guadalajara", country="MX"),
            HopLocation(ip="141.101.74.40", ts=now, located=True, lat=32.78, lon=-96.80,
                        city="Dallas", country="US"),
            HopLocation(ip="10.0.0.1", ts=now, located=False, lat=None, lon=None,
                        city=None, country=None),
        ])
        s.commit()
    with get_session() as s:
        geo = queries.geo_map(s, network_id=None)
    assert geo.path_target == "1.1.1.1"
    assert [h.hop for h in geo.path] == [2, 3]  # hop 1 (private/unlocated) skipped, in order
    assert geo.path[1].city == "Dallas"
    assert geo.path[1].rtt_ms == 50.0

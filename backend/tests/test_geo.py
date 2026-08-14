import time
from pathlib import Path

from netpulse.api import queries
from netpulse.db.models import AnycastPop, PingRaw
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

"""Real-time (UDP/QUIC) media-path quality probe.

The passive TCP probe (`ss -ti`) is blind to calls and games, which ride UDP/QUIC. UDP sockets carry
no kernel RTT, so instead we detect an active UDP media flow (`ss -uan`) and ICMP-ping its actual
remote peer — that RTT/loss/jitter is the path the call/game experiences. No synthetic reflector
needed; it measures the real endpoint you're talking to right now.
"""

from __future__ import annotations

from netpulse import shell
from netpulse.db.models import MediaRaw
from netpulse.probes import ping
from netpulse.probes.flows import _classify, _rdns, extract_remotes


async def sample(ts: float, _iface: str) -> MediaRaw | None:
    """The busiest active UDP peer's live path quality, or None when no UDP media flow is active or
    the peer can't be ICMP-measured. (`ss -uan` lists all UDP sockets — many WebRTC/RTP flows use
    unconnected sockets whose peer is `*:*`; extract_remotes keeps only concrete public peers.)"""
    res = await shell.run("ss", "-uan", timeout=5)
    counts = extract_remotes(res.stdout)
    if not counts:
        return None
    remote_ip, endpoints = max(counts.items(), key=lambda kv: kv[1])
    pinged = await ping.sample(ts, remote_ip)
    # Media servers routinely filter/rate-limit ICMP: a failed ping (or a measurement gap) means
    # "no signal", NOT 100 % media loss. Trusting it would flag a good call as degraded (the
    # ICMP-filter trap).
    if pinged is None or pinged.rtt_avg is None:
        return None
    rdns = await _rdns(remote_ip)
    return MediaRaw(
        ts=ts,
        remote_ip=remote_ip,
        app=_classify(rdns),
        endpoints=endpoints,
        rtt_ms=pinged.rtt_avg,
        loss_pct=pinged.loss_pct,
        jitter_ms=pinged.jitter,
    )

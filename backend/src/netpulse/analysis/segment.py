"""Local-vs-transit latency decomposition (fixability discriminator).

Answers: does the latency accumulate in the ISP access/backhaul (operator/your-zone — not
user-fixable) or beyond the ISP border in transit (international routing — a VPN might help)?

Crucially it does NOT trust intermediate-hop ICMP RTTs (routers deprioritize TTL-expired ICMP,
so a mid-path hop routinely shows tens of ms while packets through it exit fast — the audit
proved this). Instead it anchors on **reliable end-to-end** measurements: the best-peered
destination's RTT is a clean proxy for access+local-peering quality; if even that is slow the
access is the problem, otherwise the excess is transit-side. Pure and unit-tested.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass

_ACCESS_HEAVY_MS = 40.0  # if the best-peered path is already this slow, the access itself is heavy


@dataclass(frozen=True, slots=True)
class SegmentVerdict:
    local_rtt: float | None  # best-peered destination RTT — proxy for access + local peering
    dest_rtt: float | None  # worst/degraded destination RTT
    transit_ms: float | None  # dest - local = latency beyond the ISP border
    layer: str  # "access" | "transit" | "balanced" | "unknown"


def is_private(ip: str) -> bool:
    """RFC1918 + CGNAT (100.64/10) + link-local — i.e. inside the ISP / not yet on the internet."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return addr.is_private or addr in ipaddress.ip_network("100.64.0.0/10")


def classify(local_rtt: float | None, dest_rtt: float | None) -> SegmentVerdict:
    if local_rtt is None or dest_rtt is None:
        return SegmentVerdict(local_rtt, dest_rtt, None, "unknown")
    transit = max(0.0, dest_rtt - local_rtt)
    if local_rtt >= _ACCESS_HEAVY_MS and local_rtt >= transit:
        layer = "access"  # even the best-peered path is slow → the ISP access/backhaul
    elif transit >= _ACCESS_HEAVY_MS and transit > local_rtt:
        layer = "transit"  # the best path is fine; the excess is beyond the ISP border
    else:
        layer = "balanced"
    return SegmentVerdict(local_rtt=local_rtt, dest_rtt=dest_rtt, transit_ms=transit, layer=layer)

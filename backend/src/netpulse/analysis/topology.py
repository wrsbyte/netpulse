"""Network architecture inference — is the topology optimal, or is something misconfigured?

End-to-end numbers can't tell a double-NAT from a clean single router, or a mesh you're roaming
well on from a repeater halving your throughput. This reads the shape of the network from the
route (leading private hops), the public IP (CGNAT), and the neighbour scan (same-SSID APs) and
names concrete misconfigurations. Pure and unit-tested.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from ipaddress import ip_address

from netpulse.analysis.wifi_channel import ssid_root

_STUCK_MARGIN_DB = 8.0  # a same-SSID AP this much stronger than the one you're on = you're stuck


def _in(ip: str, cidr: str) -> bool:
    try:
        net = ip_address(ip)
        base, bits = cidr.split("/")
        return int(net) >> (32 - int(bits)) == int(ip_address(base)) >> (32 - int(bits))
    except ValueError:
        return False


_PRIVATE = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16")


def is_private(ip: str) -> bool:
    return any(_in(ip, c) for c in _PRIVATE)


def is_cgnat(ip: str | None) -> bool:
    return bool(ip) and _in(ip, "100.64.0.0/10")  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class TopologyVerdict:
    ap_count: int  # distinct BSSIDs sharing your SSID (1 = single AP, >1 = mesh / multiple APs)
    is_mesh: bool
    double_nat: bool
    cgnat: bool
    stuck_on_far_ap: bool  # a same-SSID AP is much stronger than the one you're associated with
    wired: bool
    leading_private_hops: int
    lan_devices: int | None = None  # resolved devices on your LAN (None = not measured)
    problems: list[str] = field(default_factory=list)


def _leading_private(hop_hosts: list[str | None]) -> int:
    n = 0
    for host in hop_hosts:
        if host and is_private(host):
            n += 1
        elif host:  # first resolved public hop ends the private prefix
            break
    return n


def analyze_topology(
    hop_hosts: list[str | None],
    public_ipv4: str | None,
    own_ssid: str | None,
    own_bssid: str | None,
    own_signal_dbm: float | None,
    scan: list[tuple[str | None, str | None, float]],  # (ssid, bssid, signal_dbm)
    *,
    wired: bool,
    lan_devices: int | None = None,
) -> TopologyVerdict:
    leading = _leading_private(hop_hosts)
    # A home double-NAT is a SHORT private prefix (your router + one upstream router) then public.
    # A long private chain (5-10 hops) is the ISP's own private/CGNAT access network, not a second
    # router in your home — flagging that as "double-NAT" cries wolf on every cable ISP.
    double_nat = 2 <= leading <= 3
    cgnat = is_cgnat(public_ipv4) or any(h and is_cgnat(h) for h in hop_hosts)

    root = ssid_root(own_ssid)
    same_ssid = {b for s, b, _ in scan if b and root and ssid_root(s) == root}
    if own_bssid:
        same_ssid.add(own_bssid)
    ap_count = len(same_ssid)
    strongest_other = max(
        (sig for s, b, sig in scan if b and b != own_bssid and root and ssid_root(s) == root),
        default=None,
    )
    stuck = (
        own_signal_dbm is not None
        and strongest_other is not None
        and strongest_other - own_signal_dbm >= _STUCK_MARGIN_DB
    )

    problems: list[str] = []
    if double_nat:
        problems.append("double-nat")
    if cgnat:
        problems.append("cgnat")
    if stuck:
        problems.append("stuck-on-far-ap")
    return TopologyVerdict(
        ap_count=ap_count, is_mesh=ap_count > 1, double_nat=double_nat, cgnat=cgnat,
        stuck_on_far_ap=bool(stuck), wired=wired, leading_private_hops=leading,
        lan_devices=lan_devices, problems=problems,
    )

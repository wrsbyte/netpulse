"""Passive transport-quality probe — the kernel's own view of the user's real flows.

`ss -tin` exposes per-socket tcp_info: smoothed RTT, base (min) RTT, retransmits, and achieved
delivery rate. That is *real experienced* RTT/loss/goodput on the destinations the user actually
talks to, at zero probe cost and in both directions — the ground truth ICMP only approximates.
Parsing is pure and unit-tested; endpoints are aggregated and ASN/app-enriched like flows.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from netpulse import shell
from netpulse.db.models import FlowQuality
from netpulse.probes.flows import _REMOTE as _PEER
from netpulse.probes.flows import _asn, _classify, _is_public, _rdns

_RTT = re.compile(r"\brtt:([\d.]+)/")
_MIN_RTT = re.compile(r"\bmin_?rtt:([\d.]+)")  # iproute2 prints "minrtt:", some builds "min_rtt:"
_RETRANS = re.compile(r"\bretrans:\d+/(\d+)")
_DELIVERY = re.compile(r"\bdelivery_rate:?\s*([\d.]+)([KMG]?)bps")
_UNIT = {"": 1e-6, "K": 1e-3, "M": 1.0, "G": 1e3}  # -> Mbps

_MAX_ENDPOINTS = 40


@dataclass(slots=True)
class SocketInfo:
    peer_ip: str
    srtt: float | None
    min_rtt: float | None
    retrans: int | None
    delivery_mbps: float | None


def _f(pattern: re.Pattern[str], text: str) -> float | None:
    m = pattern.search(text)
    return float(m.group(1)) if m else None


def parse_ss_ti(text: str) -> list[SocketInfo]:
    """Pair each socket line (peer IP) with its following indented tcp_info line."""
    lines = text.splitlines()
    out: list[SocketInfo] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if "rtt:" in line:  # an info line without a preceding socket line — skip
            i += 1
            continue
        peer = _PEER.search(line)
        info = lines[i + 1] if i + 1 < len(lines) and "rtt:" in lines[i + 1] else None
        if peer and info is not None:
            deliver = _DELIVERY.search(info)
            mbps = float(deliver.group(1)) * _UNIT[deliver.group(2)] if deliver else None
            retr = _RETRANS.search(info)
            out.append(SocketInfo(
                peer_ip=peer.group(1),
                srtt=_f(_RTT, info),
                min_rtt=_f(_MIN_RTT, info),
                retrans=int(retr.group(1)) if retr else None,
                delivery_mbps=mbps,
            ))
            i += 2
        else:
            i += 1
    return out


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


async def sample(ts: float, _iface: str) -> list[FlowQuality]:
    res = await shell.run("ss", "-tin", "state", "established", timeout=6)
    by_ip: dict[str, list[SocketInfo]] = {}
    for sock in parse_ss_ti(res.stdout):
        if _is_public(sock.peer_ip):
            by_ip.setdefault(sock.peer_ip, []).append(sock)

    top = sorted(by_ip.items(), key=lambda kv: len(kv[1]), reverse=True)[:_MAX_ENDPOINTS]
    rows: list[FlowQuality] = []
    for ip, socks in top:
        rdns = await _rdns(ip)
        rows.append(FlowQuality(
            ts=ts, remote_ip=ip, asn=await _asn(ip), app=_classify(rdns),
            srtt_ms=_mean([s.srtt for s in socks if s.srtt is not None]),
            min_rtt_ms=_mean([s.min_rtt for s in socks if s.min_rtt is not None]),
            retrans_total=max((s.retrans for s in socks if s.retrans is not None), default=None),
            delivery_mbps=_mean([s.delivery_mbps for s in socks if s.delivery_mbps is not None]),
            sockets=len(socks),
        ))
    return rows

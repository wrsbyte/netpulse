"""Active-connection probe — top remote endpoints classified by application/CDN.

Snapshots established TCP connections (``ss``), aggregates by public remote IP, then
enriches each with reverse DNS, ASN (Team Cymru whois-over-DNS) and a coarse application
label (Google/YouTube/GitHub/Meta…). Per-process attribution is out of scope (needs root).
"""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket

from netpulse import shell
from netpulse.db.models import Flow

# `ss -tan state established` drops the State column, so match the peer address (last
# addr:port on the line). Brackets around IPv6 are stripped by the caller.
_REMOTE = re.compile(r"\[?([0-9a-fA-F.:]+)\]?:\d+\s*$", re.MULTILINE)
_ASN = re.compile(r'"?(\d+)\s*\|')

# rDNS/SNI substring -> application label. First match wins.
_APP_MAP: tuple[tuple[str, str], ...] = (
    ("1e100.net", "Google"),
    ("googlevideo", "YouTube"),
    ("googleusercontent", "Google"),
    ("google", "Google"),
    ("gstatic", "Google"),
    ("github", "GitHub"),
    ("githubusercontent", "GitHub"),
    ("fbcdn", "Meta"),
    ("facebook", "Meta"),
    ("whatsapp", "WhatsApp"),
    ("akamai", "Akamai CDN"),
    ("cloudfront", "CloudFront"),
    ("fastly", "Fastly"),
    ("cloudflare", "Cloudflare"),
    ("microsoft", "Microsoft"),
    ("windowsupdate", "Microsoft"),
    ("apple", "Apple"),
    ("amazonaws", "AWS"),
)

_MAX_ENDPOINTS = 50


def _classify(rdns: str | None) -> str | None:
    if not rdns:
        return None
    low = rdns.lower()
    for needle, label in _APP_MAP:
        if needle in low:
            return label
    return None


def _is_public(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip).is_global
    except ValueError:
        return False


async def _rdns(ip: str) -> str | None:
    try:
        host, *_ = await asyncio.to_thread(socket.gethostbyaddr, ip)
        return host
    except (OSError, socket.herror):
        return None


async def _asn(ip: str) -> str | None:
    if ":" in ip:  # IPv6 origin lookup differs; skip for now
        return None
    reversed_ip = ".".join(reversed(ip.split(".")))
    res = await shell.run("dig", "+short", f"{reversed_ip}.origin.asn.cymru.com", "TXT", timeout=4)
    m = _ASN.search(res.stdout)
    return m.group(1) if m else None


def extract_remotes(ss_output: str) -> dict[str, int]:
    """Public peer IP -> connection count from ``ss`` output (any column layout)."""
    counts: dict[str, int] = {}
    for ip in _REMOTE.findall(ss_output):
        if _is_public(ip):
            counts[ip] = counts.get(ip, 0) + 1
    return counts


async def sample(ts: float, _iface: str) -> list[Flow]:
    res = await shell.run("ss", "-tan", "state", "established", timeout=5)
    counts = extract_remotes(res.stdout)

    top = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:_MAX_ENDPOINTS]
    rows: list[Flow] = []
    for ip, conns in top:
        rdns = await _rdns(ip)
        rows.append(
            Flow(ts=ts, remote_ip=ip, rdns=rdns, asn=await _asn(ip),
                 app=_classify(rdns), conns=conns)
        )
    return rows

"""LAN device census — how many devices share your local network.

Reads the kernel neighbour table (``ip neigh``): every host the machine has recently talked to on
the LAN. Counts resolved neighbours (REACHABLE/STALE/DELAY), excluding the gateway and unresolved
(FAILED/INCOMPLETE) entries. It answers "is it my own network that's busy, or a neighbour's AP" at
the device-count level — a genuinely empty LAN rules out your own devices as the airtime hog.
"""

from __future__ import annotations

from netpulse import shell

_RESOLVED = ("REACHABLE", "STALE", "DELAY", "PROBE")


def _count(text: str, gateway_ip: str | None) -> int:
    seen: set[str] = set()
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 2 or "lladdr" not in parts:
            continue
        ip = parts[0]
        if ip == gateway_ip or not any(state in parts for state in _RESOLVED):
            continue
        seen.add(ip)
    return len(seen)


async def sample(gateway_ip: str | None) -> int | None:
    res = await shell.run("ip", "neigh", "show", timeout=4)
    if not res.ok:
        return None
    return _count(res.stdout, gateway_ip)

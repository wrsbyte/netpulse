"""RIPEstat BGP view (free, no auth).

Fetches recent BGP updates for the user's prefix so route instability (flaps / path changes seen
by the global routing table) can be distinguished from congestion, and correlated with netpulse's
own POP-flip events. Public endpoint; failures degrade gracefully. Summarizing is pure and tested.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from netpulse.logging import get_logger

log = get_logger("ripestat")

_URL = "https://stat.ripe.net/data/bgp-updates/data.json"
_TIMEOUT = 15.0


@dataclass(frozen=True, slots=True)
class BgpSummary:
    resource: str
    announcements: int
    withdrawals: int
    total: int
    stable: bool  # few updates in the window = a stable route


def summarize(resource: str, updates: list[dict[str, object]]) -> BgpSummary:
    ann = sum(1 for u in updates if u.get("type") == "A")
    wit = sum(1 for u in updates if u.get("type") == "W")
    total = len(updates)
    return BgpSummary(
        resource=resource, announcements=ann, withdrawals=wit, total=total, stable=total <= 4
    )


async def bgp_summary(resource: str) -> BgpSummary | None:
    """Recent BGP-update activity for the prefix/IP. None on failure."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(_URL, params={"resource": resource})
            resp.raise_for_status()
            updates = resp.json().get("data", {}).get("updates", [])
            return summarize(resource, updates)
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        log.info("ripestat fetch failed", resource=resource, error=str(exc))
        return None

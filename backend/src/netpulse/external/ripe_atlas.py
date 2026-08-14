"""RIPE Atlas outside-in baseline (free, no auth).

Fetches, for a target IP, the RTT distribution measured by RIPE Atlas probes in a given country,
so the user's own RTT can be positioned as a percentile within comparable connections: the
'is it just my ISP or normal for the region?' answer that a single home vantage cannot give.

All public endpoints; network failures degrade gracefully (return None → inside-out only). The
percentile math is pure and unit-tested.
"""

from __future__ import annotations

import httpx

from netpulse.logging import get_logger

log = get_logger("ripe")

_BASE = "https://atlas.ripe.net/api/v2"
_TIMEOUT = 30.0
_MAX_PROBE_PAGES = 8  # cap the probe-list crawl (data-cheap)

# Built-in RIPE Atlas measurement 1001: IPv4 ping to k.root-servers.net, run by ~all probes.
# k-root is globally anycast, so a probe's RTT to it is a clean proxy for its regional network
# quality — the reference distribution for "is my latency normal for the region?".
K_ROOT_MSM = 1001
K_ROOT_IP = "193.0.14.129"


def percentile_rank(value: float, distribution: list[float]) -> float | None:
    """Fraction of the distribution at or below ``value`` (0-100). None if empty."""
    if not distribution:
        return None
    below = sum(1 for d in distribution if d <= value)
    return round(100 * below / len(distribution), 1)


async def _country_probe_ids(client: httpx.AsyncClient, country: str) -> set[int]:
    ids: set[int] = set()
    url: str | None = f"{_BASE}/probes/?country_code={country}&status=1&fields=id&page_size=500"
    for _ in range(_MAX_PROBE_PAGES):
        if url is None:
            break
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
        ids.update(p["id"] for p in data.get("results", []))
        url = data.get("next")
    return ids


async def regional_rtts(country: str = "MX") -> list[float] | None:
    """In-country RIPE Atlas probes' RTT to k-root (built-in msm 1001) — the regional
    network-quality reference distribution. None on failure or no in-country data."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            probe_ids = await _country_probe_ids(client, country)
            if not probe_ids:
                return None
            resp = await client.get(f"{_BASE}/measurements/{K_ROOT_MSM}/latest/")
            resp.raise_for_status()
            rtts = [
                float(r["avg"])
                for r in resp.json()
                if r.get("prb_id") in probe_ids
                and isinstance(r.get("avg"), (int, float))
                and r["avg"] > 0
            ]
            return rtts or None
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        log.info("ripe atlas fetch failed", country=country, error=str(exc))
        return None

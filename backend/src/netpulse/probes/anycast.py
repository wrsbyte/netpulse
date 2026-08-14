"""Anycast POP probe — which datacentre a CDN actually serves you from.

Cloudflare's ``https://<ip>/cdn-cgi/trace`` returns ``colo=<airport>`` (the serving POP) and
``loc=<country>`` (yours). If the POP is out-of-country while the CDN runs in-country POPs, the
ISP is hauling your traffic the long way — the single most actionable routing signal (this is
how we caught Mega Cable routing Cloudflare to Dallas instead of Querétaro). Parsing is pure and
unit-tested; the airport→country map is a focused, offline table.
"""

from __future__ import annotations

import re

from netpulse import shell
from netpulse.db.models import AnycastPop

_COLO = re.compile(r"^colo=(\w+)", re.MULTILINE)
_LOC = re.compile(r"^loc=(\w+)", re.MULTILINE)

# Cloudflare anycast targets to trace (extensible; only Cloudflare exposes a colo endpoint).
CLOUDFLARE_TARGETS = ("1.1.1.1", "1.0.0.1")

# IATA airport → ISO country for common CDN POPs (enough to decide in-country vs not).
_IATA_COUNTRY: dict[str, str] = {
    # Mexico
    "QRO": "MX", "MEX": "MX", "GDL": "MX",
    # United States
    "DFW": "US", "MIA": "US", "IAH": "US", "LAX": "US", "ATL": "US", "IAD": "US",
    "EWR": "US", "SJC": "US", "ORD": "US", "DEN": "US", "SEA": "US", "PHX": "US",
    # Latin America
    "BOG": "CO", "GRU": "BR", "GIG": "BR", "EZE": "AR", "SCL": "CL", "LIM": "PE",
    "PTY": "PA", "UIO": "EC", "SJO": "CR", "GUA": "GT", "MDE": "CO",
    # Europe
    "LHR": "GB", "CDG": "FR", "FRA": "DE", "AMS": "NL", "MAD": "ES",
}


def parse_trace(text: str) -> tuple[str | None, str | None]:
    """Return (colo airport, client country) from a cdn-cgi/trace body."""
    colo = _COLO.search(text)
    loc = _LOC.search(text)
    return (colo.group(1) if colo else None, loc.group(1) if loc else None)


def classify(
    ts: float, provider: str, target: str, colo: str | None, loc: str | None
) -> AnycastPop:
    colo_country = _IATA_COUNTRY.get(colo) if colo else None
    # Out-of-country only when we can place both and they differ (unknown airport → False).
    out = bool(colo_country and loc and colo_country != loc)
    return AnycastPop(
        ts=ts, provider=provider, target=target, colo=colo,
        colo_country=colo_country, client_country=loc, out_of_country=out,
    )


async def sample(ts: float) -> list[AnycastPop]:
    rows: list[AnycastPop] = []
    for target in CLOUDFLARE_TARGETS:
        res = await shell.run(
            "curl", "-s", "--max-time", "6", f"https://{target}/cdn-cgi/trace", timeout=8
        )
        if not res.ok:
            continue
        colo, loc = parse_trace(res.stdout)
        if colo is None:
            continue
        rows.append(classify(ts, "cloudflare", target, colo, loc))
    return rows

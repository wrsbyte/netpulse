"""DNS resolution probe — query time and success per (domain, resolver).

Uses ``dig`` against each resolver (empty resolver = the system default). Success requires
a non-empty ANSWER section; a SERVFAIL/timeout is recorded as ``ok=False`` so DNS outages
show up distinctly from connectivity outages.
"""

from __future__ import annotations

import re

from netpulse import shell
from netpulse.db.models import DnsRaw

_QTIME = re.compile(r"Query time:\s*(\d+)\s*msec")
_ANSWER = re.compile(r"ANSWER:\s*(\d+)")


async def sample(ts: float, domain: str, resolver: str, tls: bool = False) -> DnsRaw:
    """Resolve ``domain`` via ``resolver`` (empty = system). ``tls=True`` measures DNS-over-TLS
    (port 853): its timing/success is the encrypted-DNS health signal — if 853 is blocked or the
    cert fails, ok=False, surfacing an 'encrypted DNS broken' failure mode plain DNS can't show."""
    args = ["dig", "+tries=1", "+time=2"]
    if tls:
        args.append("+tls")
    if resolver:
        args.append(f"@{resolver}")
    args += [domain, "A"]
    res = await shell.run(*args, timeout=5)

    answer_m = _ANSWER.search(res.stdout)
    ok = res.ok and answer_m is not None and int(answer_m.group(1)) > 0
    qtime_m = _QTIME.search(res.stdout)
    label = resolver or "system"
    return DnsRaw(
        ts=ts,
        domain=domain,
        resolver=f"{label} (DoT)" if tls else label,
        query_ms=float(qtime_m.group(1)) if qtime_m else None,
        ok=ok,
    )

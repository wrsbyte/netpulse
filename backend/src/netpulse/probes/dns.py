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


async def sample(ts: float, domain: str, resolver: str) -> DnsRaw:
    args = ["dig", "+tries=1", "+time=2"]
    if resolver:
        args.append(f"@{resolver}")
    args += [domain, "A"]
    res = await shell.run(*args, timeout=4)

    answer_m = _ANSWER.search(res.stdout)
    ok = res.ok and answer_m is not None and int(answer_m.group(1)) > 0
    qtime_m = _QTIME.search(res.stdout)
    return DnsRaw(
        ts=ts,
        domain=domain,
        resolver=resolver or "system",
        query_ms=float(qtime_m.group(1)) if qtime_m else None,
        ok=ok,
    )

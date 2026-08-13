"""Public IP probe — current egress IPv4/IPv6 (for change detection).

Returns the addresses only; the collector diffs against stored state and logs an event on
change. Uses Cloudflare's trace endpoint (works while most of the internet is unreachable).
"""

from __future__ import annotations

import re

from netpulse import shell

_IP = re.compile(r"^ip=(\S+)", re.MULTILINE)

_URL = "https://one.one.one.one/cdn-cgi/trace"


async def _fetch(flag: str) -> str | None:
    res = await shell.run("curl", flag, "-s", "--max-time", "5", _URL, timeout=6)
    m = _IP.search(res.stdout)
    return m.group(1) if m else None


async def sample() -> tuple[str | None, str | None]:
    return await _fetch("-4"), await _fetch("-6")

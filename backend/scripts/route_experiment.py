#!/usr/bin/env python
"""Route-discrimination experiment.

Probes a curated set of real destinations (Colombian gov, US gov, and services behind
different CDNs/hosting) to test one hypothesis directly: is the degradation *route-specific*
(international transit / a particular CDN peering) rather than "the whole internet"? Each host
is resolved, ASN-tagged, and pinged with enough packets for a trustworthy loss estimate, then
grouped so the local-peered vs international split (and any per-CDN loss) is visible.

Run: uv run python scripts/route_experiment.py
"""

from __future__ import annotations

import asyncio
import re
import statistics
from dataclasses import dataclass

from netpulse import shell

# (hostname, category) — chosen to separate local peering from international transit and to
# isolate whether specific CDNs (Cloudflare) are worse than others on this ISP.
TARGETS: list[tuple[str, str]] = [
    ("1.1.1.1", "anycast-dns/cloudflare"),
    ("1.0.0.1", "anycast-dns/cloudflare"),
    ("8.8.8.8", "anycast-dns/google"),
    ("9.9.9.9", "anycast-dns/quad9"),
    ("208.67.222.222", "anycast-dns/opendns"),
    ("www.gov.co", "co-gov"),
    ("www.dian.gov.co", "co-gov"),
    ("www.presidencia.gov.co", "co-gov"),
    ("www.mintic.gov.co", "co-gov"),
    ("www.eltiempo.com", "co-media"),
    ("www.bancolombia.com", "co-bank"),
    ("www.usa.gov", "us-gov"),
    ("www.nasa.gov", "us-gov"),
    ("www.irs.gov", "us-gov"),
    ("www.cdc.gov", "us-gov"),
    ("www.cloudflare.com", "cdn-cloudflare"),
    ("www.microsoft.com", "cdn-akamai"),
    ("www.apple.com", "cdn-akamai"),
    ("www.amazon.com", "cdn-cloudfront"),
    ("github.com", "svc-github"),
    ("www.netflix.com", "svc-netflix"),
    ("www.wikipedia.org", "svc-wikimedia"),
    ("web.whatsapp.com", "svc-meta"),
    ("www.youtube.com", "svc-google"),
]

_LOSS = re.compile(r"(\d+(?:\.\d+)?)% packet loss")
_RTT = re.compile(r"= ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)")
_ASN = re.compile(r'"?(\d+)\s*\|')
_PACKETS = 30


@dataclass
class Result:
    host: str
    category: str
    ip: str | None
    asn: str | None
    avg: float | None
    p95: float | None
    loss: float | None
    jitter: float | None


async def _resolve(host: str) -> str | None:
    if re.match(r"^\d+\.\d+\.\d+\.\d+$", host):
        return host
    res = await shell.run("dig", "+short", "@8.8.8.8", host, "A", timeout=5)
    for line in res.stdout.splitlines():
        if re.match(r"^\d+\.\d+\.\d+\.\d+$", line.strip()):
            return line.strip()
    return None


async def _asn(ip: str) -> str | None:
    rev = ".".join(reversed(ip.split(".")))
    res = await shell.run("dig", "+short", f"{rev}.origin.asn.cymru.com", "TXT", timeout=5)
    m = _ASN.search(res.stdout)
    return m.group(1) if m else None


async def _probe(host: str, category: str, sem: asyncio.Semaphore) -> Result:
    async with sem:
        ip = await _resolve(host)
        if ip is None:
            return Result(host, category, None, None, None, None, None, None)
        asn = await _asn(ip)
        res = await shell.run(
            "ping", "-n", "-c", str(_PACKETS), "-i", "0.2", "-w", "12", ip, timeout=15
        )
        loss_m = _LOSS.search(res.stdout)
        rtt_m = _RTT.search(res.stdout)
        loss = float(loss_m.group(1)) if loss_m else 100.0
        if rtt_m:
            return Result(
                host, category, ip, asn,
                avg=float(rtt_m.group(2)), p95=None, loss=loss, jitter=float(rtt_m.group(4)),
            )
        return Result(host, category, ip, asn, None, None, loss, None)


async def main() -> None:
    sem = asyncio.Semaphore(8)
    results = await asyncio.gather(*(_probe(h, c, sem) for h, c in TARGETS))
    ordered = sorted(results, key=lambda r: (r.avg if r.avg is not None else 9999))

    print(f"{'host':26}{'category':22}{'ASN':>7}{'avg':>7}{'loss%':>7}{'jit':>6}  IP")
    print("-" * 92)
    for r in ordered:
        avg = f"{r.avg:.0f}" if r.avg is not None else "--"
        jit = f"{r.jitter:.0f}" if r.jitter is not None else "--"
        loss = f"{r.loss:.1f}" if r.loss is not None else "--"
        asn = f"AS{r.asn}" if r.asn else "?"
        ip = r.ip or "no-dns"
        print(f"{r.host[:24]:26}{r.category:22}{asn:>7}{avg:>7}{loss:>7}{jit:>6}  {ip}")

    ok = [r for r in results if r.avg is not None]
    fast = [r for r in ok if r.avg is not None and r.avg < 40]
    slow = [r for r in ok if r.avg is not None and r.avg >= 70]
    lossy = [r for r in ok if r.loss and r.loss >= 2]
    print("\n=== VERDICT ===")
    if fast:
        print(f"local/well-peered (<40ms): {len(fast)}  median RTT "
              f"{statistics.median([r.avg for r in fast]):.0f}ms  "
              f"median loss {statistics.median([r.loss or 0 for r in fast]):.1f}%")
    if slow:
        print(f"international (>=70ms):     {len(slow)}  median RTT "
              f"{statistics.median([r.avg for r in slow]):.0f}ms  "
              f"median loss {statistics.median([r.loss or 0 for r in slow]):.1f}%")
    if lossy:
        print("lossy (>=2%): " + ", ".join(f"{r.host}({r.loss:.1f}%,AS{r.asn})" for r in lossy))


if __name__ == "__main__":
    asyncio.run(main())

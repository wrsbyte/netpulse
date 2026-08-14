#!/usr/bin/env python
"""A/B test: does a VPN/WARP fix the degraded path?

Measures RTT + loss to a target for a baseline period, asks you to enable your VPN/WARP, then
measures again, and reports the change with a block-bootstrap 95% CI (a real, significance-tested
answer — not a before/after eyeball). Lower RTT/loss whose CI excludes zero = the VPN helps.

Run: uv run python scripts/ab_vpn.py [target] [cycles]
Note: a simple before/after can be confounded by a time trend; for a rigorous result run it a few
times, or alternate on/off. This is the quick, actionable check.
"""

from __future__ import annotations

import asyncio
import sys
import time

from netpulse.analysis.experiment import ab_compare
from netpulse.probes import ping


async def _collect(target: str, cycles: int) -> tuple[list[float], list[float]]:
    rtts: list[float] = []
    losses: list[float] = []
    for i in range(cycles):
        row = await ping.sample(time.time(), target)
        losses.append(row.loss_pct)
        if row.rtt_avg is not None:
            rtts.append(row.rtt_avg)
        print(f"  {i + 1}/{cycles}  rtt={row.rtt_avg}  loss={row.loss_pct}%", end="\r")
    print()
    return rtts, losses


def _report(name: str, unit: str, before: list[float], after: list[float]) -> None:
    r = ab_compare(before, after)
    if r is None:
        print(f"{name}: not enough data")
        return
    verdict = (
        "VPN HELPS" if r.improved else "VPN WORSE" if r.significant else "no significant change"
    )
    print(
        f"{name}: {r.a_mean:.1f} -> {r.b_mean:.1f} {unit} "
        f"(delta {r.delta:+.1f}, 95% CI {r.ci_lo:+.1f}..{r.ci_hi:+.1f}) -> {verdict}"
    )


async def main() -> None:
    target = sys.argv[1] if len(sys.argv) > 1 else "1.1.1.1"
    cycles = int(sys.argv[2]) if len(sys.argv) > 2 else 40
    print(f"Baseline (VPN OFF) to {target} — {cycles} cycles:")
    b_rtt, b_loss = await _collect(target, cycles)
    await asyncio.to_thread(
        input, "\nEnable your VPN / Cloudflare WARP now, then press Enter to measure again..."
    )
    print(f"\nTreatment (VPN ON) to {target} — {cycles} cycles:")
    a_rtt, a_loss = await _collect(target, cycles)
    print("\n=== RESULT ===")
    _report("RTT ", "ms", b_rtt, a_rtt)
    _report("Loss", "%", b_loss, a_loss)


if __name__ == "__main__":
    asyncio.run(main())

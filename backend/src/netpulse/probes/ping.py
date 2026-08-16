"""ICMP ping probe — RTT (min/avg/max), packet loss %, jitter (mdev)."""

from __future__ import annotations

import re

from netpulse import shell
from netpulse.db.models import PingRaw

# Loss is computed from the transmitted/received COUNTS, not read from the printed "%": the counts
# are authoritative and reproducible for any packet count, and a printed "20%" only ever meant
# "1 of 5 dropped" — a coarse, single-packet event (typically ICMP rate-limiting), not a stable
# path-loss rate. Handles both "N received" (iputils) and "N packets received" (busybox).
_COUNTS = re.compile(r"(\d+) packets transmitted, (\d+)(?: packets)? received")
_RTT = re.compile(r"= ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)")  # min/avg/max/mdev

# 10 packets/cycle: finer loss resolution (10% steps, not 25%) and more RTT samples for jitter.
# -W 1 (per-reply timeout), NOT -w (overall deadline): a deadline lets ping keep sending past -c
# whenever a reply is late, so a lossy cycle transmitted 11-15 packets and the loss denominator
# drifted (1/11 = 9.09% instead of a clean 1/10). -W caps each wait, so exactly _COUNT go out and
# the sample size (hence the loss %) is deterministic. Completes in ~1.9 s, within the 3 s cadence.
_COUNT = 10


async def sample(ts: float, target: str, af: str = "4") -> PingRaw | None:
    res = await shell.run(
        "ping", "-n", "-c", str(_COUNT), "-i", "0.2", "-W", "1", target, timeout=6
    )
    counts = _COUNTS.search(res.stdout)
    if counts is None:
        # ping produced no summary line (binary missing, killed by the timeout, or garbled output).
        # That is an instrument gap, NOT a 100%-loss outage — the old `else 100.0` default here
        # fabricated false outages. Report nothing; the collector skips a missing sample.
        return None
    sent, recv = int(counts.group(1)), int(counts.group(2))
    loss = 100.0 * (sent - recv) / sent if sent else 100.0
    rtt_m = _RTT.search(res.stdout)
    if rtt_m:
        mn, avg, mx, mdev = (float(rtt_m.group(i)) for i in (1, 2, 3, 4))
        return PingRaw(
            ts=ts, target=target, af=af, loss_pct=loss,
            rtt_min=mn, rtt_avg=avg, rtt_max=mx, jitter=mdev,
        )
    return PingRaw(ts=ts, target=target, af=af, loss_pct=loss)

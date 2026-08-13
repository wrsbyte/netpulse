"""ICMP ping probe — RTT (min/avg/max), packet loss %, jitter (mdev)."""

from __future__ import annotations

import re

from netpulse import shell
from netpulse.db.models import PingRaw

_LOSS = re.compile(r"(\d+(?:\.\d+)?)% packet loss")
_RTT = re.compile(r"= ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)")  # min/avg/max/mdev


async def sample(ts: float, target: str) -> PingRaw:
    res = await shell.run("ping", "-n", "-c", "4", "-i", "0.2", "-w", "3", target, timeout=6)
    loss_m = _LOSS.search(res.stdout)
    loss = float(loss_m.group(1)) if loss_m else 100.0
    rtt_m = _RTT.search(res.stdout)
    if rtt_m:
        mn, avg, mx, mdev = (float(rtt_m.group(i)) for i in (1, 2, 3, 4))
        return PingRaw(
            ts=ts, target=target, loss_pct=loss,
            rtt_min=mn, rtt_avg=avg, rtt_max=mx, jitter=mdev,
        )
    return PingRaw(ts=ts, target=target, loss_pct=loss)

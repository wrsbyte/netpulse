"""Path probe — per-hop loss and RTT toward a target.

Prefers ``mtr`` (raw sockets, needs a scoped ``sudo -n`` NOPASSWD entry) for loss-per-hop;
falls back to unprivileged ``tracepath``. Returns one row per hop; empty if neither runs.
"""

from __future__ import annotations

import re

from netpulse import shell
from netpulse.db.models import Traceroute

# mtr --report line: " 1.|-- 192.168.100.1  0.0%  3  1.2  1.3  ..."
_MTR = re.compile(r"\s*\d+\.\|--\s+(\S+)\s+([\d.]+)%\s+\d+\s+[\d.]+\s+([\d.]+)")
# tracepath line: " 1:  192.168.100.1  1.234ms"
_TRACEPATH = re.compile(r"\s*(\d+):\s+(\S+)\s+([\d.]+)ms")


async def sample(ts: float, target: str) -> list[Traceroute]:
    if shell.have("mtr"):
        res = await shell.run(
            "sudo", "-n", "mtr", "-n", "--report", "--report-cycles", "3", target, timeout=30
        )
        if res.ok:
            return [
                Traceroute(
                    ts=ts, target=target, hop=i + 1,
                    host=m.group(1), loss_pct=float(m.group(2)), rtt_ms=float(m.group(3)),
                )
                for i, m in enumerate(_MTR.finditer(res.stdout))
            ]

    res = await shell.run("tracepath", "-n", target, timeout=30)
    rows: list[Traceroute] = []
    for m in _TRACEPATH.finditer(res.stdout):
        rows.append(
            Traceroute(
                ts=ts, target=target, hop=int(m.group(1)),
                host=m.group(2), loss_pct=None, rtt_ms=float(m.group(3)),
            )
        )
    return rows

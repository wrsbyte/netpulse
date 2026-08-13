"""Interface throughput probe — RX/TX bits per second from kernel byte counters.

Reads ``/sys/class/net/<iface>/statistics/{rx,tx}_bytes`` and differences against the
previous read. The first call primes the baseline and returns ``None`` (no delta yet).
"""

from __future__ import annotations

from pathlib import Path

from netpulse.db.models import ThroughputRaw

_last: dict[str, tuple[float, int, int]] = {}  # iface -> (ts, rx_bytes, tx_bytes)


def _counter(iface: str, direction: str) -> int:
    return int(Path(f"/sys/class/net/{iface}/statistics/{direction}_bytes").read_text())


async def sample(ts: float, iface: str) -> ThroughputRaw | None:
    try:
        rx, tx = _counter(iface, "rx"), _counter(iface, "tx")
    except (FileNotFoundError, ValueError):
        return None

    prev = _last.get(iface)
    _last[iface] = (ts, rx, tx)
    if prev is None:
        return None
    dt = ts - prev[0]
    if dt <= 0:
        return None
    return ThroughputRaw(
        ts=ts,
        rx_bps=max(0, rx - prev[1]) * 8 / dt,
        tx_bps=max(0, tx - prev[2]) * 8 / dt,
    )

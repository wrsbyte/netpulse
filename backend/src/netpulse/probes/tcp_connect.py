"""Active TCP-connect latency probe.

Times the TCP handshake (SYN→SYN/ACK) to a port — the honest "would a real connection be slow"
metric. Unlike ICMP it is forwarding-plane (not router-deprioritized) and reaches hosts that
filter ping, so an ICMP-filtered destination becomes a real `filtered`/`refused`/`ok` state
instead of a fake 100% loss.
"""

from __future__ import annotations

import asyncio
import contextlib

from netpulse.db.models import TcpConnect


async def measure(target: str, port: int, timeout: float = 5.0) -> TcpConnect:  # noqa: ASYNC109
    clock = asyncio.get_running_loop().time
    start = clock()
    try:
        fut = asyncio.open_connection(target, port)
        _, writer = await asyncio.wait_for(fut, timeout)
        elapsed = (clock() - start) * 1000
        writer.close()
        with contextlib.suppress(Exception):
            await writer.wait_closed()
        return TcpConnect(target=target, port=port, connect_ms=elapsed, status="ok")
    except ConnectionRefusedError:
        return TcpConnect(target=target, port=port, connect_ms=None, status="refused")
    except (TimeoutError, OSError):
        return TcpConnect(target=target, port=port, connect_ms=None, status="filtered")


async def sample(ts: float, targets: list[tuple[str, int]]) -> list[TcpConnect]:
    # Sequential, not concurrent: parallel handshakes share the uplink and inflate each other's
    # latency (a fast target read 118 ms next to slow ones, 14 ms alone).
    rows: list[TcpConnect] = []
    for host, port in targets:
        row = await measure(host, port)
        row.ts = ts
        rows.append(row)
    return rows

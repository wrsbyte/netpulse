"""Neighboring-AP scan — channel congestion map.

Uses ``nmcli`` (no root, no association drop with ``--rescan no``) to list visible APs with
channel and signal, so the dashboard can show APs-per-channel and recommend a clearer one.
"""

from __future__ import annotations

from netpulse import shell
from netpulse.db.models import WifiScan


async def sample(ts: float, _iface: str) -> list[WifiScan]:
    res = await shell.run(
        "nmcli", "-t", "-f", "CHAN,SIGNAL,SSID,BSSID", "dev", "wifi", "list", "--rescan", "no",
        timeout=8,
    )
    if not res.ok:
        return []
    rows: list[WifiScan] = []
    for line in res.stdout.splitlines():
        # nmcli terse escapes ':' in the BSSID as '\:'; split on unescaped ':'.
        parts = _split_terse(line)
        if len(parts) < 4 or not parts[0]:
            continue
        try:
            chan, signal = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        rows.append(
            WifiScan(
                ts=ts, channel=chan,
                signal_dbm=signal / 2 - 100,  # nmcli 0-100 quality -> approx dBm
                ssid=parts[2] or None, bssid=parts[3] or None,
            )
        )
    return rows


def _split_terse(line: str) -> list[str]:
    out: list[str] = []
    field = ""
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == "\\" and i + 1 < len(line):
            field += line[i + 1]
            i += 2
            continue
        if ch == ":":
            out.append(field)
            field = ""
        else:
            field += ch
        i += 1
    out.append(field)
    return out

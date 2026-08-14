"""WiFi disconnect events from the system journal.

Reads wpa_supplicant CTRL-EVENT-DISCONNECTED lines and, crucially, their ``locally_generated``
flag: a locally-generated deauth is the *laptop* leaving (suspend / lid-close / power-save), not
the network failing. This lets the verdict stop miscounting the user's own suspends as outages.
Parsing is pure and unit-tested; requires journal read access (degrades to nothing without it).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from netpulse import shell

_LINE = re.compile(
    r"^(\d+)\.\d+ .*CTRL-EVENT-DISCONNECTED.*?reason=(\d+)(?:\s+locally_generated=(\d))?"
)


@dataclass(frozen=True, slots=True)
class Disconnect:
    ts: float
    reason: int
    local: bool  # locally_generated=1 -> the laptop initiated it


def parse(text: str) -> list[Disconnect]:
    out: list[Disconnect] = []
    for line in text.splitlines():
        m = _LINE.match(line)
        if m:
            out.append(Disconnect(
                ts=float(m.group(1)), reason=int(m.group(2)), local=m.group(3) == "1",
            ))
    return out


async def since(ts: float) -> list[Disconnect]:
    res = await shell.run(
        "journalctl", "-o", "short-unix", "--no-pager", "-g", "CTRL-EVENT-DISCONNECTED",
        "--since", f"@{int(ts)}", timeout=6,
    )
    if not res.ok:
        return []
    return [d for d in parse(res.stdout) if d.ts > ts]

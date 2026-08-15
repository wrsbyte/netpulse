"""WiFi channel-congestion analysis.

netpulse already scans neighbouring APs; this turns that into an actionable finding: how many
APs share your current channel, and which clean 5 GHz channel to move to. On 5 GHz the low band
(36/40/44/48, UNII-1) has no DFW/radar so no risk of radar-triggered drops. Pure, unit-tested.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

# 80 MHz blocks by primary channel. An 80 MHz link occupies its whole block, so congestion is a
# per-block property: a neighbour on 40 competes with you on 36. UNII-1 and UNII-3 are non-DFS
# (no radar-triggered drops), so they're the safe blocks to pin an 80 MHz link to.
_BLOCKS_5G = {
    36: (36, 40, 44, 48),  # UNII-1
    149: (149, 153, 157, 161, 165),  # UNII-3
}
_CROWDED = 3  # strong neighbour APs in your block at/above which acting is worth it
_CONTEND_FLOOR = -85.0  # dBm; a neighbour weaker than this barely competes for airtime

_BAND_SUFFIX = re.compile(r"[-_ ]?(2\.?4|5)\s*g?(hz)?$", re.IGNORECASE)


def ssid_root(ssid: str | None) -> str | None:
    """Strip a trailing band tag so a router's per-band SSIDs collapse to one identity — e.g.
    ``INFINITUM38B5_5`` and ``INFINITUM38B5_2.4`` both become ``INFINITUM38B5``. Used to stop
    counting your own router's other radio as a competing neighbour."""
    if not ssid:
        return ssid
    return _BAND_SUFFIX.sub("", ssid).strip() or ssid


def _block_primary(channel: int | None) -> int | None:
    if channel is None:
        return None
    for primary, channels in _BLOCKS_5G.items():
        if channel in channels:
            return primary
    return None


@dataclass(frozen=True, slots=True)
class ChannelAdvice:
    current: int | None
    aps_on_current: int
    best_alternative: int | None
    alternative_aps: int
    crowded: bool
    recommend_narrow: bool = False  # narrowing the width de-contends without changing channel


def continuous_hours(samples: list[tuple[float, int | None]], current: int | None) -> float | None:
    """How long (hours) you've been continuously on ``current``, walking back from the latest
    sample until the channel changes. ``samples`` are ``(ts, channel)`` ascending by ts. This is
    what turns "you're on 149" into "you've been stuck on 149 for 8 h" — the actionable part."""
    if current is None or not samples:
        return None
    latest_ts = samples[-1][0]
    earliest = latest_ts
    for ts, channel in reversed(samples):
        if channel != current:
            break
        earliest = ts
    return (latest_ts - earliest) / 3600.0


def analyze(
    current: int | None,
    neighbours: list[tuple[int, float]],
    width_mhz: int | None = None,
) -> ChannelAdvice:
    """Which non-DFS 80 MHz block is cleanest. ``neighbours`` are ``(channel, signal_dbm)`` of OTHER
    APs (your own AP/router excluded upstream). Only APs above the contention floor count: a distant
    -90 dBm AP barely shares your airtime, so it must never push you off a clean channel onto a
    busier one. When the crowding sits in your block but not on your primary 20 MHz slice, the fix
    is to narrow the width (escape the overlap) rather than move channel."""
    counts = Counter(ch for ch, sig in neighbours if sig >= _CONTEND_FLOOR)
    current_block = _block_primary(current)
    if current_block is None:
        on_current = counts.get(current, 0) if current is not None else 0
        return ChannelAdvice(current, on_current, None, 0, False)
    assert current is not None  # _block_primary(None) is None, so we returned above

    def block_aps(primary: int) -> int:
        return sum(counts.get(ch, 0) for ch in _BLOCKS_5G[primary])

    on_current = block_aps(current_block)
    on_primary = counts.get(current, 0)
    alternatives = sorted((p for p in _BLOCKS_5G if p != current_block), key=block_aps)
    best = alternatives[0] if alternatives else None
    best_aps = block_aps(best) if best is not None else 0
    crowded = on_current >= _CROWDED
    recommend_narrow = crowded and (width_mhz or 0) > 20 and on_primary < _CROWDED
    move = crowded and not recommend_narrow and best is not None and best_aps < on_current
    return ChannelAdvice(
        current=current, aps_on_current=on_current,
        best_alternative=best if move else None, alternative_aps=best_aps,
        crowded=crowded, recommend_narrow=recommend_narrow,
    )

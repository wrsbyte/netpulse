"""WiFi channel-congestion analysis.

netpulse already scans neighbouring APs; this turns that into an actionable finding: how many
APs share your current channel, and which clean 5 GHz channel to move to. On 5 GHz the low band
(36/40/44/48, UNII-1) has no DFW/radar so no risk of radar-triggered drops. Pure, unit-tested.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

# 80 MHz blocks by primary channel. An 80 MHz link occupies its whole block, so congestion is a
# per-block property: a neighbour on 40 competes with you on 36. UNII-1 and UNII-3 are non-DFS
# (no radar-triggered drops), so they're the safe blocks to pin an 80 MHz link to.
_BLOCKS_5G = {
    36: (36, 40, 44, 48),  # UNII-1
    149: (149, 153, 157, 161, 165),  # UNII-3
}
_CROWDED = 4  # neighbour APs in your 80 MHz block at/above which moving blocks is worth it


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


def analyze(current: int | None, scan_channels: list[int]) -> ChannelAdvice:
    """Which non-DFS 80 MHz block is cleanest. ``scan_channels`` is the neighbours' channels (your
    own AP excluded upstream). On 5 GHz, congestion is counted per block; the fallback for 2.4 GHz
    or an unknown channel is the single-channel count."""
    counts = Counter(scan_channels)
    current_block = _block_primary(current)
    if current_block is None:
        on_current = counts.get(current, 0) if current is not None else 0
        return ChannelAdvice(current, on_current, None, 0, False)

    def block_aps(primary: int) -> int:
        return sum(counts.get(ch, 0) for ch in _BLOCKS_5G[primary])

    on_current = block_aps(current_block)
    alternatives = sorted((p for p in _BLOCKS_5G if p != current_block), key=block_aps)
    best = alternatives[0] if alternatives else None
    best_aps = block_aps(best) if best is not None else 0
    crowded = on_current >= _CROWDED and best is not None and best_aps < on_current
    return ChannelAdvice(
        current=current, aps_on_current=on_current,
        best_alternative=best if crowded else None, alternative_aps=best_aps, crowded=crowded,
    )

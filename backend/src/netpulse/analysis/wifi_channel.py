"""WiFi channel-congestion analysis.

netpulse already scans neighbouring APs; this turns that into an actionable finding: how many
APs share your current channel, and which clean 5 GHz channel to move to. On 5 GHz the low band
(36/40/44/48, UNII-1) has no DFW/radar so no risk of radar-triggered drops. Pure, unit-tested.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

# 5 GHz UNII-1 channels: no DFS (no radar-detection drops), safe to pin.
_CLEAN_5G = (36, 40, 44, 48)
_CROWDED = 4  # APs on your channel (including you) at/above which it's worth moving


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
    counts = Counter(scan_channels)
    on_current = counts.get(current, 0) if current is not None else 0
    # Pick the least-crowded clean channel that isn't the current one.
    candidates = sorted(
        (ch for ch in _CLEAN_5G if ch != current), key=lambda ch: counts.get(ch, 0)
    )
    best = candidates[0] if candidates else None
    best_aps = counts.get(best, 0) if best is not None else 0
    crowded = on_current >= _CROWDED and best is not None and best_aps < on_current
    return ChannelAdvice(
        current=current, aps_on_current=on_current,
        best_alternative=best if crowded else None, alternative_aps=best_aps, crowded=crowded,
    )

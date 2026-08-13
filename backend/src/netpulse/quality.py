"""Derived quality scores — pure functions, no I/O, unit-tested.

* :func:`mos` — Mean Opinion Score (1-5) from the ITU-T G.107 E-model, the telco
  formula for "how good would a call sound" given latency/jitter/loss.
* :func:`bufferbloat_grade` — A+..F from the latency added under load (loaded - idle RTT),
  the Bufferbloat.net methodology.
* :func:`percentile` — linear-interpolated percentile (for the p95 smoke bands).
"""

from __future__ import annotations

from bisect import bisect_left

# Bufferbloat grade thresholds: added latency under load (ms) -> letter.
_BUFFERBLOAT_BANDS: tuple[tuple[float, str], ...] = (
    (5, "A+"),
    (30, "A"),
    (60, "B"),
    (100, "C"),
    (200, "D"),
)


def percentile(values: list[float], pct: float) -> float:
    """Linear-interpolated percentile. ``pct`` in [0, 100]. Empty -> 0.0."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (pct / 100) * (len(ordered) - 1)
    lo = int(rank)
    frac = rank - lo
    if lo + 1 >= len(ordered):
        return ordered[-1]
    return ordered[lo] + frac * (ordered[lo + 1] - ordered[lo])


def bufferbloat_grade(idle_ms: float, loaded_ms: float) -> tuple[float, str]:
    """Return (added latency ms, grade). Grade reflects the increase, not absolute RTT."""
    added = max(0.0, loaded_ms - idle_ms)
    idx = bisect_left([b[0] for b in _BUFFERBLOAT_BANDS], added)
    grade = _BUFFERBLOAT_BANDS[idx][1] if idx < len(_BUFFERBLOAT_BANDS) else "F"
    return added, grade


def mos(latency_ms: float, jitter_ms: float, loss_pct: float) -> float:
    """ITU-T G.107 E-model → MOS in [1.0, 4.5]. Effective latency folds in jitter."""
    effective_latency = latency_ms + 2 * jitter_ms + 10.0
    if effective_latency < 160:
        r = 93.2 - effective_latency / 40
    else:
        r = 93.2 - (effective_latency - 120) / 10
    r -= 2.5 * loss_pct  # each 1% loss costs ~2.5 R-points

    if r < 0:
        return 1.0
    if r > 100:
        return 4.5
    score = 1 + 0.035 * r + r * (r - 60) * (100 - r) * 7e-6
    return round(score, 2)

"""Small, dependency-free statistics for the analysis layer.

Pure functions, unit-tested: Pearson correlation (evidence for attribution), EWMA and a robust
z-score (median + MAD) for anomaly detection against a rolling baseline. Kept in stdlib math
so the collector/API carry no numpy dependency for a handful of series.
"""

from __future__ import annotations

from statistics import median


def pearson(xs: list[float], ys: list[float]) -> float | None:
    """Correlation coefficient in [-1, 1], or None if undefined (n<2 or a flat series)."""
    n = min(len(xs), len(ys))
    if n < 2:
        return None
    xs, ys = xs[:n], ys[:n]
    mx = sum(xs) / n
    my = sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx == 0 or vy == 0:
        return None
    return float(cov / (vx**0.5 * vy**0.5))


def ewma(values: list[float], alpha: float = 0.3) -> float | None:
    """Exponentially-weighted moving average (recent-weighted baseline)."""
    if not values:
        return None
    acc = values[0]
    for v in values[1:]:
        acc = alpha * v + (1 - alpha) * acc
    return acc


def mad(values: list[float]) -> float:
    """Median absolute deviation — a robust (outlier-resistant) spread measure."""
    if not values:
        return 0.0
    med = median(values)
    return median([abs(v - med) for v in values])


def robust_z(value: float, baseline: list[float]) -> float | None:
    """How anomalous ``value`` is vs its baseline, in robust std-devs. None if no spread."""
    if len(baseline) < 3:
        return None
    med = median(baseline)
    spread = mad(baseline)
    if spread == 0:
        return None
    # 1.4826 scales MAD to be consistent with the standard deviation for normal data.
    return (value - med) / (1.4826 * spread)

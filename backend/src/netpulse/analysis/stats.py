"""Small, dependency-free statistics for the analysis layer.

Pure functions, unit-tested: Pearson correlation (evidence for attribution), EWMA and a robust
z-score (median + MAD) for anomaly detection against a rolling baseline. Kept in stdlib math
so the collector/API carry no numpy dependency for a handful of series.
"""

from __future__ import annotations

import random
from statistics import median

from netpulse.quality import percentile


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


def _ranks(values: list[float]) -> list[float]:
    """Fractional ranks (ties share the average rank) — the basis for Spearman."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        shared = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = shared
        i = j + 1
    return ranks


def spearman(xs: list[float], ys: list[float]) -> float | None:
    """Rank correlation — robust to non-linearity and the heavy-tailed count data we correlate
    (loss vs retry-rate), where Pearson's linearity/normality assumptions don't hold."""
    n = min(len(xs), len(ys))
    if n < 2:
        return None
    return pearson(_ranks(xs[:n]), _ranks(ys[:n]))


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


def autocorr1(xs: list[float]) -> float:
    """Lag-1 autocorrelation. 0 for constant/too-short series."""
    n = len(xs)
    if n < 2:
        return 0.0
    mean = sum(xs) / n
    denom = sum((x - mean) ** 2 for x in xs)
    if denom == 0:
        return 0.0
    num = sum((xs[i] - mean) * (xs[i + 1] - mean) for i in range(n - 1))
    return num / denom


def effective_n(xs: list[float]) -> float:
    """Autocorrelation-adjusted sample size n*(1-r)/(1+r) with r the lag-1 autocorrelation:
    network series are not i.i.d., so the naive n over-states the information and shrinks CIs."""
    r = autocorr1(xs)
    if r <= 0:
        return float(len(xs))
    return len(xs) * (1 - r) / (1 + r)


def block_bootstrap_ci(
    xs: list[float], block: int = 10, samples: int = 500, level: float = 0.95, seed: int = 12345
) -> tuple[float, float]:
    """95% CI on the mean by moving-block bootstrap — resamples contiguous blocks so the burst
    structure (autocorrelation) is preserved, unlike an i.i.d. bootstrap or Wilson."""
    n = len(xs)
    if n == 0:
        return (0.0, 0.0)
    if n <= block:
        return (min(xs), max(xs))
    rng = random.Random(seed)
    n_blocks = -(-n // block)  # ceil
    max_start = n - block
    means: list[float] = []
    for _ in range(samples):
        acc: list[float] = []
        for _ in range(n_blocks):
            s = rng.randint(0, max_start)
            acc.extend(xs[s : s + block])
        acc = acc[:n]
        means.append(sum(acc) / len(acc))
    means.sort()
    lo = (1 - level) / 2
    return (percentile(means, lo * 100), percentile(means, (1 - lo) * 100))


def gilbert_elliott(bad: list[bool]) -> tuple[float, float]:
    """From a good/bad (loss) series: (fraction bad, mean bad-burst length). Distinguishes '3%
    as one long outage' from '3% spread uniformly' — different cause, different experience."""
    if not bad:
        return (0.0, 0.0)
    frac = sum(bad) / len(bad)
    bursts: list[int] = []
    run = 0
    for b in bad:
        if b:
            run += 1
        elif run:
            bursts.append(run)
            run = 0
    if run:
        bursts.append(run)
    mean_burst = sum(bursts) / len(bursts) if bursts else 0.0
    return (frac, mean_burst)


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

"""A/B intervention comparison (e.g. VPN/WARP off vs on).

Compares a metric between two epochs with a block-bootstrap CI on the difference of means, so
the "does a VPN fix it?" question is answered with a significance-tested delta, not a
before/after eyeball. Lower-is-better metrics (latency, loss): a negative delta whose CI
excludes zero is a real improvement. Pure and unit-tested.

For a rigorous result the two epochs should be *interleaved* blocks (ABAB), not one long
before then one long after, so a time trend cancels — the caller (the A/B script) arranges that.
"""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ABResult:
    a_mean: float
    b_mean: float
    delta: float  # b - a (negative = improvement for lower-is-better metrics)
    ci_lo: float
    ci_hi: float
    significant: bool  # CI on the delta excludes zero
    improved: bool  # significantly lower (better)


def _block_resample_mean(xs: list[float], block: int, rng: random.Random) -> float:
    n = len(xs)
    if n <= block:
        return sum(xs) / n
    max_start = n - block
    acc: list[float] = []
    while len(acc) < n:
        s = rng.randint(0, max_start)
        acc.extend(xs[s : s + block])
    acc = acc[:n]
    return sum(acc) / len(acc)


def ab_compare(
    before: list[float], after: list[float], block: int = 10, samples: int = 500, seed: int = 7
) -> ABResult | None:
    """None if either arm is empty; otherwise the delta (after-before) with a 95% block-bootstrap
    CI that respects the burst structure of network series."""
    if not before or not after:
        return None
    a_mean = sum(before) / len(before)
    b_mean = sum(after) / len(after)
    rng = random.Random(seed)
    deltas = [
        _block_resample_mean(after, block, rng) - _block_resample_mean(before, block, rng)
        for _ in range(samples)
    ]
    deltas.sort()
    lo = deltas[int(0.025 * samples)]
    hi = deltas[min(samples - 1, int(0.975 * samples))]
    significant = lo > 0 or hi < 0
    return ABResult(
        a_mean=a_mean, b_mean=b_mean, delta=b_mean - a_mean,
        ci_lo=lo, ci_hi=hi, significant=significant, improved=significant and hi < 0,
    )

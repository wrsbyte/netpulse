"""Composite health score — turns a window's metrics into one A-F grade.

Each sub-metric is mapped to a 0-100 sub-score by a documented best/worst band (piecewise
linear, clamped), then combined by fixed weights. Pure and unit-tested; the weights and bands
are the whole model, so they live here explicitly rather than scattered.
"""

from __future__ import annotations

from dataclasses import dataclass

# weight, best (→100), worst (→0). "best/worst" may descend (higher availability is better).
# Loss is handled separately (non-linear) — a linear 0→10% band scores 2% loss as 80, but 2%
# loss already breaks calls; see _loss_sub_score.
_BANDS: dict[str, tuple[float, float, float]] = {
    "loss": (0.30, 0.0, 10.0),  # placeholder weight; mapping is non-linear (see _loss_sub_score)
    "latency": (0.25, 30.0, 300.0),  # p95 RTT (ms) to internet targets
    "jitter": (0.15, 5.0, 50.0),  # ms
    "bufferbloat": (0.20, 5.0, 200.0),  # ms added under load
    "availability": (0.10, 100.0, 90.0),  # % of window with internet reachable
}

# Metrics that can single-handedly make a link unusable: the grade is capped near their worst
# sub-score, so a healthy average can't hide catastrophic loss or downtime (gating, not mean).
_CRITICAL = ("loss", "availability")
_GATE_MARGIN = 25.0


@dataclass(frozen=True, slots=True)
class HealthInputs:
    loss: float | None
    latency: float | None
    jitter: float | None
    bufferbloat: float | None
    availability: float | None


@dataclass(frozen=True, slots=True)
class HealthScore:
    score: float  # 0-100
    grade: str  # A+ .. F
    breakdown: dict[str, float]  # per-metric sub-score (only for metrics we had data for)


def _sub_score(value: float, best: float, worst: float) -> float:
    span = worst - best
    if span == 0:
        return 100.0
    frac = (value - best) / span
    return max(0.0, min(100.0, 100.0 * (1 - frac)))


def _loss_sub_score(loss_pct: float) -> float:
    """Convex loss penalty: 0%→100, 1%→60, 2%→36, 5%→8, 10%→~0.6. Sub-percent moves the grade
    (linear bands don't), matching how loss actually destroys VoIP/video."""
    return max(0.0, float(100.0 * 0.6**loss_pct))


def _metric_sub_score(key: str, value: float) -> float:
    if key == "loss":
        return _loss_sub_score(value)
    _, best, worst = _BANDS[key]
    return _sub_score(value, best, worst)


def _grade(score: float) -> str:
    if score >= 97:
        return "A+"
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def health(inputs: HealthInputs) -> HealthScore:
    """Weighted score over whichever metrics have data; missing metrics drop out and the
    remaining weights renormalize, so a window without a speedtest still grades fairly."""
    values = {
        "loss": inputs.loss,
        "latency": inputs.latency,
        "jitter": inputs.jitter,
        "bufferbloat": inputs.bufferbloat,
        "availability": inputs.availability,
    }
    breakdown: dict[str, float] = {}
    weighted_sum = 0.0
    total_weight = 0.0
    for key, value in values.items():
        if value is None:
            continue
        sub = _metric_sub_score(key, value)
        weight = _BANDS[key][0]
        breakdown[key] = round(sub, 1)
        weighted_sum += weight * sub
        total_weight += weight

    mean = weighted_sum / total_weight if total_weight else 0.0
    # Gating: a critical metric near its floor caps the grade, so a good average can't hide a
    # link that is actually unusable (e.g. 10% loss must be F, not a mean-diluted C).
    critical = [breakdown[k] for k in _CRITICAL if k in breakdown]
    score = min(mean, min(critical) + _GATE_MARGIN) if critical else mean
    score = round(score, 1)
    return HealthScore(score=score, grade=_grade(score), breakdown=breakdown)

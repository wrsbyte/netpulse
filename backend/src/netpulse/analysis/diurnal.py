"""Diurnal (hour-of-day) analysis.

Groups a metric's samples by local hour to answer "is it worse at peak hours?". Reports each
hour's mean with a block-bootstrap CI and sample count, plus how many distinct days were
observed — because a claim of *diurnality* needs the pattern to repeat across days, not a single
afternoon's slope (the audit's correction). Bucketing is pure and unit-tested.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from netpulse.analysis.stats import block_bootstrap_ci


@dataclass(frozen=True, slots=True)
class HourCell:
    hour: int
    mean: float
    ci_lo: float
    ci_hi: float
    n: int


def local_hour(ts: float) -> int:
    return datetime.fromtimestamp(ts).hour


def local_day(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def bucket_by_hour(samples: list[tuple[float, float]]) -> dict[int, list[float]]:
    """Group (ts, value) pairs by local hour-of-day."""
    out: dict[int, list[float]] = {}
    for ts, value in samples:
        out.setdefault(local_hour(ts), []).append(value)
    return out


def distinct_days(samples: list[tuple[float, float]]) -> int:
    return len({local_day(ts) for ts, _ in samples})


def hourly_cells(samples: list[tuple[float, float]]) -> list[HourCell]:
    """One cell per populated hour: mean + block-bootstrap 95% CI + sample count."""
    cells: list[HourCell] = []
    for hour, values in sorted(bucket_by_hour(samples).items()):
        lo, hi = block_bootstrap_ci(values) if len(values) > 10 else (min(values), max(values))
        cells.append(HourCell(
            hour=hour, mean=sum(values) / len(values), ci_lo=lo, ci_hi=hi, n=len(values),
        ))
    return cells

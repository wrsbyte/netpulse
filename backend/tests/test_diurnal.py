from datetime import datetime

from netpulse.analysis.diurnal import bucket_by_hour, distinct_days, hourly_cells


def _ts(day: int, hour: int) -> float:
    return datetime(2026, 8, day, hour, 30).timestamp()


def test_bucket_by_local_hour() -> None:
    samples = [(_ts(1, 9), 10.0), (_ts(2, 9), 20.0), (_ts(1, 21), 5.0)]
    buckets = bucket_by_hour(samples)
    assert sorted(buckets[9]) == [10.0, 20.0]
    assert buckets[21] == [5.0]


def test_distinct_days_counts_calendar_days() -> None:
    assert distinct_days([(_ts(1, 9), 1.0), (_ts(1, 22), 1.0), (_ts(3, 9), 1.0)]) == 2


def test_hourly_cells_summarize_each_hour() -> None:
    samples = [(_ts(1, 20), 100.0) for _ in range(20)] + [(_ts(1, 4), 10.0) for _ in range(20)]
    cells = {c.hour: c for c in hourly_cells(samples)}
    assert cells[20].mean == 100.0 and cells[20].n == 20
    assert cells[4].mean == 10.0

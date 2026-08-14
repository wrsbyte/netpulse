from netpulse.analysis.experiment import ab_compare


def test_clear_improvement_is_significant() -> None:
    before = [100.0 + (i % 5) for i in range(100)]  # ~102
    after = [40.0 + (i % 5) for i in range(100)]  # ~42
    r = ab_compare(before, after)
    assert r is not None
    assert r.delta < 0
    assert r.significant and r.improved
    assert r.ci_hi < 0


def test_no_difference_is_not_significant() -> None:
    before = [50.0 + (i % 7) for i in range(100)]
    after = [50.0 + ((i + 3) % 7) for i in range(100)]
    r = ab_compare(before, after)
    assert r is not None
    assert not r.significant
    assert not r.improved


def test_empty_arm_returns_none() -> None:
    assert ab_compare([], [1.0, 2.0]) is None

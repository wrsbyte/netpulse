import pytest

from netpulse.analysis.stats import ewma, mad, pearson, robust_z, spearman


def test_pearson_perfect_and_flat() -> None:
    assert pearson([1, 2, 3, 4], [2, 4, 6, 8]) == pytest.approx(1.0)
    assert pearson([1, 2, 3], [3, 2, 1]) == pytest.approx(-1.0)
    assert pearson([1, 1, 1], [1, 2, 3]) is None  # flat x -> undefined
    assert pearson([1], [2]) is None  # n<2


def test_ewma_weights_recent() -> None:
    assert ewma([]) is None
    assert ewma([5.0]) == 5.0
    rising = ewma([0, 0, 0, 10], alpha=0.5)
    assert rising is not None and rising > 1.0


def test_spearman_catches_monotonic_nonlinear() -> None:
    # Perfectly monotonic but non-linear: Spearman = 1 where Pearson would be < 1.
    xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    ys = [1.0, 4.0, 9.0, 16.0, 25.0]
    s = spearman(xs, ys)
    assert s == pytest.approx(1.0)
    assert pearson(xs, ys) < 1.0


def test_mad_and_robust_z_flag_outliers() -> None:
    baseline = [10, 11, 9, 10, 12, 8, 10]
    assert mad(baseline) > 0
    z = robust_z(30, baseline)  # far above the baseline
    assert z is not None and z > 5
    assert robust_z(10, [10, 10, 10]) is None  # no spread -> undefined

import pytest

from netpulse.analysis.stats import (
    autocorr1,
    block_bootstrap_ci,
    effective_n,
    ewma,
    gilbert_elliott,
    mad,
    pearson,
    robust_z,
    spearman,
)


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


def test_autocorr_and_effective_n() -> None:
    # A strongly autocorrelated (blocky) series has effective n well below its length.
    blocky = [0.0] * 20 + [10.0] * 20
    assert autocorr1(blocky) > 0.8
    assert effective_n(blocky) < len(blocky) / 3
    # An alternating (negatively-correlated) series is not penalised.
    assert effective_n([0.0, 1.0] * 20) == 40


def test_block_bootstrap_ci_brackets_the_mean() -> None:
    xs = [float(i) for i in range(200)]  # mean 99.5, blocks vary
    lo, hi = block_bootstrap_ci(xs, block=10, samples=400)
    assert lo < 99.5 < hi


def test_gilbert_elliott_separates_burst_from_uniform() -> None:
    # Same 20% loss: one long burst vs uniformly scattered — different mean burst length.
    bursty = [False] * 8 + [True] * 2 + [False] * 8 + [True] * 2
    uniform = [True, False, False, False, False] * 4
    fb, burst_b = gilbert_elliott(bursty)
    fu, burst_u = gilbert_elliott(uniform)
    assert fb == pytest.approx(0.2) and fu == pytest.approx(0.2)
    assert burst_b > burst_u  # bursts of 2 vs isolated single losses


def test_mad_and_robust_z_flag_outliers() -> None:
    baseline = [10, 11, 9, 10, 12, 8, 10]
    assert mad(baseline) > 0
    z = robust_z(30, baseline)  # far above the baseline
    assert z is not None and z > 5
    assert robust_z(10, [10, 10, 10]) is None  # no spread -> undefined

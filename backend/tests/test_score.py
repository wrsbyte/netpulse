from netpulse.analysis.score import HealthInputs, health


def test_perfect_link_grades_a() -> None:
    s = health(HealthInputs(loss=0, latency=20, jitter=2, bufferbloat=3, availability=100))
    assert s.grade in ("A", "A+")
    assert s.score >= 90


def test_lossy_link_grades_low() -> None:
    s = health(HealthInputs(loss=8, latency=250, jitter=40, bufferbloat=180, availability=92))
    assert s.grade in ("D", "F")
    assert s.score < 60


def test_missing_metrics_renormalize() -> None:
    # Only loss known; score reflects it alone rather than punishing absent metrics.
    perfect = health(HealthInputs(loss=0, latency=None, jitter=None, bufferbloat=None, availability=None))  # noqa: E501
    assert perfect.score == 100.0
    assert set(perfect.breakdown) == {"loss"}


def test_empty_inputs_score_zero() -> None:
    s = health(HealthInputs(None, None, None, None, None))
    assert s.score == 0.0
    assert s.breakdown == {}

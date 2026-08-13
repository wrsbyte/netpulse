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


def test_high_loss_gates_grade_to_f_despite_good_averages() -> None:
    # The audit's case: 10% loss with everything else green must NOT dilute to a C.
    s = health(HealthInputs(loss=10, latency=20, jitter=2, bufferbloat=3, availability=100))
    assert s.grade == "F"
    assert s.score < 60


def test_loss_penalty_is_convex_near_zero() -> None:
    # 1% loss is a B-ish annoyance; 2% loss is materially worse (D territory) — not both "80".
    one = health(HealthInputs(loss=1, latency=20, jitter=2, bufferbloat=3, availability=100))
    two = health(HealthInputs(loss=2, latency=20, jitter=2, bufferbloat=3, availability=100))
    assert one.score > two.score
    assert two.grade in ("C", "D", "F")


def test_empty_inputs_score_zero() -> None:
    s = health(HealthInputs(None, None, None, None, None))
    assert s.score == 0.0
    assert s.breakdown == {}

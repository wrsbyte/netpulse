from netpulse.quality import bufferbloat_grade, mos, percentile


def test_percentile_interpolates() -> None:
    assert percentile([10, 20, 30, 40], 50) == 25.0
    assert percentile([], 95) == 0.0
    assert percentile([42], 95) == 42.0


def test_bufferbloat_grade_bands() -> None:
    assert bufferbloat_grade(20, 22) == (2.0, "A+")
    assert bufferbloat_grade(20, 45) == (25.0, "A")
    assert bufferbloat_grade(20, 500)[1] == "F"


def test_mos_good_link_scores_high() -> None:
    assert mos(20, 2, 0.0) > 4.0


def test_mos_degrades_with_loss_and_latency() -> None:
    good = mos(20, 2, 0.0)
    lossy = mos(20, 2, 5.0)
    laggy = mos(300, 40, 0.0)
    assert lossy < good
    assert laggy < good
    assert 1.0 <= laggy <= 4.5

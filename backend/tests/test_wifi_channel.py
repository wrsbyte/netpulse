from netpulse.analysis.wifi_channel import analyze


def test_crowded_channel_recommends_a_clean_one() -> None:
    # 14 APs on 149 (the real case), clean low band empty -> recommend 36/40/44/48.
    scan = [149] * 14 + [11] * 5
    a = analyze(current=149, scan_channels=scan)
    assert a.aps_on_current == 14
    assert a.crowded
    assert a.best_alternative in (36, 40, 44, 48)
    assert a.alternative_aps == 0


def test_clear_channel_no_advice() -> None:
    a = analyze(current=36, scan_channels=[36, 149, 149])
    assert not a.crowded
    assert a.best_alternative is None


def test_unknown_current_is_not_crowded() -> None:
    assert not analyze(current=None, scan_channels=[149] * 10).crowded

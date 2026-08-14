from netpulse.analysis.wifi_channel import analyze, continuous_hours


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


def test_continuous_hours_counts_time_stuck_on_current_channel() -> None:
    # 8 hourly samples all on 149, then the last two on 36 (after a router change).
    base = 1_000_000.0
    samples = [(base + i * 3600, 149) for i in range(8)]
    samples += [(base + 8 * 3600, 36), (base + 9 * 3600, 36)]
    assert continuous_hours(samples, 36) == 1.0  # only the last two 36 samples, 1h apart
    # Now on 149 the whole time:
    only149 = [(base + i * 3600, 149) for i in range(9)]
    assert continuous_hours(only149, 149) == 8.0


def test_continuous_hours_none_when_no_current() -> None:
    assert continuous_hours([(1.0, 149)], None) is None
    assert continuous_hours([], 149) is None


def test_block_aware_a_neighbour_on_40_counts_against_36() -> None:
    # At 80 MHz, channel 40 is inside your 36-48 block: 4 neighbours across 36/40/44/48 make your
    # block crowded even though no single channel has 4.
    a = analyze(current=36, scan_channels=[36, 40, 44, 48])
    assert a.aps_on_current == 4  # whole block, not just ch 36
    assert a.crowded
    assert a.best_alternative == 149  # the other non-DFS block


def test_block_aware_on_the_cleanest_block_is_not_crowded() -> None:
    # 2 neighbours in your 36 block, 4 in the 149 block -> you're already on the best; stay put.
    a = analyze(current=36, scan_channels=[40, 44, 149, 153, 157, 161])
    assert a.aps_on_current == 2
    assert not a.crowded
    assert a.best_alternative is None


def test_block_aware_never_recommends_a_dfs_block() -> None:
    # Even if UNII-2 (52-64, DFS) were empty, we only offer the non-DFS blocks (36 / 149).
    a = analyze(current=149, scan_channels=[149] * 6)
    assert a.crowded
    assert a.best_alternative == 36

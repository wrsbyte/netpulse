from netpulse.analysis.wifi_channel import analyze, continuous_hours, ssid_root


def _strong(channels: list[int]) -> list[tuple[int, float]]:
    return [(ch, -60.0) for ch in channels]  # all well above the contention floor


def test_crowded_channel_recommends_a_clean_one() -> None:
    # 14 strong APs on 149, clean low band empty -> recommend 36/40/44/48.
    a = analyze(current=149, neighbours=_strong([149] * 14 + [11] * 5))
    assert a.aps_on_current == 14
    assert a.crowded
    assert a.best_alternative in (36, 40, 44, 48)
    assert a.alternative_aps == 0


def test_clear_channel_no_advice() -> None:
    a = analyze(current=36, neighbours=_strong([36, 149, 149]))
    assert not a.crowded
    assert a.best_alternative is None


def test_weak_neighbours_are_ignored() -> None:
    # 6 APs on your 149 block but all at -92 dBm (too weak to contend) -> not crowded, no move.
    a = analyze(current=149, neighbours=[(149, -92.0)] * 6)
    assert a.aps_on_current == 0
    assert not a.crowded
    assert a.best_alternative is None


def test_does_not_flee_a_clean_channel_for_a_busier_one() -> None:
    # The real Infinitum case: your 149 block has only weak neighbours (-90), while 36 has strong
    # ones. Must NOT recommend moving to the busier block.
    neighbours = [(149, -90.0), (157, -96.0), (36, -60.0), (36, -63.0), (44, -70.0)]
    a = analyze(current=149, neighbours=neighbours, width_mhz=80)
    assert not a.crowded
    assert a.best_alternative is None


def test_wide_channel_recommends_narrowing_when_primary_is_clear() -> None:
    # On 80 MHz: strong neighbours on adjacent 40/44/48 but none on your primary 36 -> narrow, not
    # move (narrowing escapes the overlap without leaving the channel).
    a = analyze(current=36, neighbours=_strong([40, 44, 48]), width_mhz=80)
    assert a.crowded
    assert a.recommend_narrow
    assert a.best_alternative is None


def test_unknown_current_is_not_crowded() -> None:
    assert not analyze(current=None, neighbours=_strong([149] * 10)).crowded


def test_continuous_hours_counts_time_stuck_on_current_channel() -> None:
    base = 1_000_000.0
    samples = [(base + i * 3600, 149) for i in range(8)]
    samples += [(base + 8 * 3600, 36), (base + 9 * 3600, 36)]
    assert continuous_hours(samples, 36) == 1.0
    only149 = [(base + i * 3600, 149) for i in range(9)]
    assert continuous_hours(only149, 149) == 8.0


def test_continuous_hours_none_when_no_current() -> None:
    assert continuous_hours([(1.0, 149)], None) is None
    assert continuous_hours([], 149) is None


def test_block_aware_a_neighbour_on_40_counts_against_36() -> None:
    a = analyze(current=36, neighbours=_strong([36, 40, 44, 48]))
    assert a.aps_on_current == 4  # whole block, not just ch 36
    assert a.crowded
    assert a.best_alternative == 149  # the other non-DFS block


def test_block_aware_never_recommends_a_dfs_block() -> None:
    a = analyze(current=149, neighbours=_strong([149] * 6))
    assert a.crowded
    assert a.best_alternative == 36


def test_ssid_root_collapses_band_suffixes() -> None:
    assert ssid_root("INFINITUM38B5_5") == "INFINITUM38B5"
    assert ssid_root("INFINITUM38B5_2.4") == "INFINITUM38B5"
    assert ssid_root("Totalplay-5G") == "Totalplay"
    assert ssid_root("PlainName") == "PlainName"
    assert ssid_root(None) is None

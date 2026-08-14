from netpulse.external.ripe_atlas import percentile_rank


def test_percentile_rank_positions_value_in_distribution() -> None:
    dist = [float(i) for i in range(100)]  # 0..99
    assert percentile_rank(50, dist) == 51.0  # 51 values are <= 50
    assert percentile_rank(-5, dist) == 0.0
    assert percentile_rank(200, dist) == 100.0


def test_percentile_rank_empty_is_none() -> None:
    assert percentile_rank(10, []) is None

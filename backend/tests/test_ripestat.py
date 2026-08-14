from netpulse.external.ripe_stat import summarize


def test_summarize_counts_and_flags_stable() -> None:
    s = summarize("177.241.60.0/22", [{"type": "A"}, {"type": "A"}, {"type": "W"}])
    assert s.announcements == 2
    assert s.withdrawals == 1
    assert s.total == 3
    assert s.stable  # <= 4 updates = stable


def test_many_updates_is_unstable() -> None:
    s = summarize("x", [{"type": "A"}] * 10)
    assert not s.stable
    assert s.announcements == 10


def test_empty_is_stable() -> None:
    assert summarize("x", []).stable

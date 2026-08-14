from netpulse.external.ripe_stat import parse_geoloc, summarize


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


def test_parse_geoloc_extracts_first_location() -> None:
    data = {"located_resources": [{"locations": [
        {"country": "US", "city": "Dallas", "latitude": 32.78, "longitude": -96.80},
    ]}]}
    loc = parse_geoloc(data)
    assert loc is not None
    assert (loc.lat, loc.lon, loc.city, loc.country) == (32.78, -96.80, "Dallas", "US")


def test_parse_geoloc_none_when_unlocated() -> None:
    assert parse_geoloc({"located_resources": []}) is None
    assert parse_geoloc({"located_resources": [{"locations": []}]}) is None

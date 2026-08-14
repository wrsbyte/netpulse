from netpulse.analysis.segment import classify, is_private


def test_is_private_covers_rfc1918_and_cgnat() -> None:
    assert is_private("192.168.100.1")
    assert is_private("10.3.5.48")
    assert is_private("100.100.0.1")  # CGNAT
    assert not is_private("1.1.1.1")
    assert not is_private("201.174.250.209")


def test_transit_when_best_path_is_fast_but_destination_slow() -> None:
    # Best-peered target 15ms (access is fine), degraded target 98ms -> transit.
    v = classify(local_rtt=15.0, dest_rtt=98.0)
    assert v.transit_ms == 83.0
    assert v.layer == "transit"


def test_access_when_even_the_best_path_is_slow() -> None:
    # Even the closest destination is 60ms -> the access/backhaul itself is heavy.
    v = classify(local_rtt=60.0, dest_rtt=75.0)
    assert v.layer == "access"


def test_balanced_when_both_low() -> None:
    assert classify(local_rtt=12.0, dest_rtt=20.0).layer == "balanced"


def test_unknown_without_data() -> None:
    assert classify(None, 50.0).layer == "unknown"

from netpulse.analysis.local_attribution import attribute_local


def test_local_when_gateway_jitter_matches_end_to_end() -> None:
    # The Infinitum case: spread to the gateway (~78 ms) is as large as to the internet (~88 ms) ->
    # the variance is born on the WiFi link.
    v = attribute_local(gw_jitter_ms=78.0, e2e_jitter_ms=88.0, gw_loss_pct=0.0, e2e_loss_pct=0.0)
    assert v is not None
    assert v.layer == "local"


def test_access_when_gateway_is_steady_but_path_swings() -> None:
    # Rock-solid gateway (1 ms spread), jittery internet (60 ms) -> the problem is past the gateway.
    v = attribute_local(gw_jitter_ms=1.0, e2e_jitter_ms=60.0, gw_loss_pct=0.0, e2e_loss_pct=0.0)
    assert v is not None
    assert v.layer == "access"


def test_ok_when_both_sides_are_calm() -> None:
    v = attribute_local(gw_jitter_ms=1.0, e2e_jitter_ms=4.0, gw_loss_pct=0.0, e2e_loss_pct=0.0)
    assert v is not None
    assert v.layer == "ok"


def test_local_when_gateway_itself_loses_packets() -> None:
    v = attribute_local(gw_jitter_ms=2.0, e2e_jitter_ms=3.0, gw_loss_pct=4.0, e2e_loss_pct=4.0)
    assert v is not None
    assert v.layer == "local"


def test_none_without_a_gateway_signal() -> None:
    assert attribute_local(None, 50.0, 0.0, 0.0) is None
    assert attribute_local(50.0, None, 0.0, 0.0) is None

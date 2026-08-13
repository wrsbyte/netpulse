from netpulse.analysis.attribute import HopStat, attribute


def _path(*losses: float) -> list[HopStat]:
    return [HopStat(hop=i + 1, host=f"hop{i + 1}", loss_pct=loss) for i, loss in enumerate(losses)]


def test_no_loss_is_none() -> None:
    a = attribute(_path(0, 0, 0, 0), loss_retry_corr=None, wifi_weak=False)
    assert a.layer == "none"


def test_mid_hop_only_is_artifact() -> None:
    # Loss at a middle hop but the destination is clean -> ICMP rate-limit noise, not a fault.
    a = attribute(_path(0, 40, 0, 0), loss_retry_corr=None, wifi_weak=False)
    assert a.layer == "none"


def test_first_hop_loss_with_retry_correlation_is_wifi() -> None:
    a = attribute(_path(20, 22, 21, 20), loss_retry_corr=0.8, wifi_weak=False)
    assert a.layer == "wifi-radio"
    assert a.hop == 1


def test_first_hop_loss_clean_radio_is_gateway() -> None:
    a = attribute(_path(15, 16, 15, 15), loss_retry_corr=0.1, wifi_weak=False)
    assert a.layer == "lan-gateway"


def test_loss_starting_beyond_gateway_is_isp() -> None:
    a = attribute(_path(0, 0, 12, 14, 13), loss_retry_corr=0.1, wifi_weak=False)
    assert a.layer == "isp"
    assert a.hop == 3
    assert a.host == "hop3"


def test_mid_spike_before_clean_stretch_is_not_the_origin() -> None:
    # Hop 2 spikes (artifact) then hops 3 is clean; real loss persists from hop 4 to the end.
    a = attribute(_path(0, 40, 0, 12, 14), loss_retry_corr=0.1, wifi_weak=False)
    assert a.layer == "isp"
    assert a.hop == 4  # not hop 2

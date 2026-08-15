from netpulse.probes.lan_census import _count

_SAMPLE = """192.168.1.254 dev wlan0 lladdr bc:d2:06:d4:81:27 REACHABLE
192.168.1.72 dev wlan0 lladdr f0:35:75:42:ed:d5 STALE
192.168.1.99 dev wlan0 lladdr aa:bb:cc:dd:ee:ff DELAY
192.168.1.50 dev wlan0  FAILED
192.168.1.51 dev wlan0 lladdr 11:22:33:44:55:66 INCOMPLETE
"""


def test_counts_resolved_devices_excluding_gateway() -> None:
    # Gateway excluded; FAILED/INCOMPLETE excluded; only the 2 resolved non-gateway devices count.
    assert _count(_SAMPLE, gateway_ip="192.168.1.254") == 2


def test_counts_gateway_when_not_named() -> None:
    assert _count(_SAMPLE, gateway_ip=None) == 3  # now the gateway row counts too


def test_empty_table_is_zero() -> None:
    assert _count("", gateway_ip="192.168.1.254") == 0

from netpulse.probes.wifi_events import parse

JOURNAL = """1786600000.123456 shfsas wpa_supplicant[691]: wlan0: CTRL-EVENT-DISCONNECTED bssid=58:25:75:41:c3:ec reason=3 locally_generated=1
1786600100.500000 shfsas wpa_supplicant[691]: wlan0: CTRL-EVENT-DISCONNECTED bssid=58:25:75:41:c3:ec reason=2
1786600200.000000 shfsas wpa_supplicant[691]: wlan0: CTRL-EVENT-DISCONNECTED bssid=58:25:75:41:c3:ec reason=4 locally_generated=1
"""  # noqa: E501


def test_parse_reason_and_locally_generated() -> None:
    events = parse(JOURNAL)
    assert len(events) == 3
    assert events[0].reason == 3 and events[0].local is True
    assert events[1].reason == 2 and events[1].local is False  # remote (network-initiated)
    assert events[2].reason == 4 and events[2].local is True


def test_parse_ignores_unrelated_lines() -> None:
    assert parse("1786600000.0 host kernel: something else\n") == []

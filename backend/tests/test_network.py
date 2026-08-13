from netpulse.probes.network import build_key


def test_key_prefers_gateway_mac() -> None:
    # Same AP, different DHCP-assigned gateway IP -> same key (MAC anchors it).
    a = build_key("aa:bb:cc:dd:ee:ff", "192.168.1.1", "Home")
    b = build_key("aa:bb:cc:dd:ee:ff", "10.0.0.1", "Home")
    assert a == b


def test_key_distinguishes_networks() -> None:
    home = build_key("aa:bb:cc:dd:ee:ff", "192.168.1.1", "Home")
    office = build_key("11:22:33:44:55:66", "192.168.1.1", "Office")
    assert home != office


def test_wired_has_no_ssid_component() -> None:
    assert build_key("aa:bb:cc:dd:ee:ff", "192.168.1.1", None).endswith("|wired")

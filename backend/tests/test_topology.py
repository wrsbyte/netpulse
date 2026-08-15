from netpulse.analysis.topology import analyze_topology, is_cgnat, is_private


def test_private_and_cgnat_ranges() -> None:
    assert is_private("192.168.1.254") and is_private("10.0.81.249") and is_private("172.16.3.1")
    assert not is_private("8.8.8.8")
    assert is_cgnat("100.100.0.5") and not is_cgnat("8.8.8.8") and not is_cgnat(None)


def test_double_nat_from_two_leading_private_hops() -> None:
    hops = ["192.168.1.254", "10.0.0.1", "187.214.7.245", "1.1.1.1"]
    t = analyze_topology(hops, "187.224.12.225", "Net_5", "aa", -50.0, [], wired=False)
    assert t.double_nat
    assert t.leading_private_hops == 2


def test_single_router_is_not_double_nat() -> None:
    hops = ["192.168.1.254", "200.38.193.226", "1.1.1.1"]
    t = analyze_topology(hops, "187.224.12.225", "Net_5", "aa", -50.0, [], wired=False)
    assert not t.double_nat
    assert t.leading_private_hops == 1


def test_long_private_chain_is_isp_access_not_double_nat() -> None:
    # Mega Cable: gateway then a long private/CGNAT-style access network (172.22, 10.3.x) before the
    # first public hop. That is the ISP's access network, NOT a second router in the home.
    hops = [
        "192.168.100.1", "172.22.144.2", "10.3.5.49", "10.0.81.249", "201.174.154.21", "1.1.1.1",
    ]
    t = analyze_topology(hops, "187.1.1.1", "CASA_5", "aa", -50.0, [], wired=False)
    assert not t.double_nat
    assert t.leading_private_hops == 4


def test_cgnat_flagged_from_public_ip() -> None:
    t = analyze_topology(
        ["192.168.0.1", "9.9.9.9"], "100.72.5.9", "N", "aa", -50.0, [], wired=False
    )
    assert t.cgnat


def test_mesh_and_stuck_on_far_ap() -> None:
    # Two BSSIDs share the SSID root; you're on the -70 one while a -55 one is in range.
    scan = [("HOME_5", "ap-far", -70.0), ("HOME_2.4", "ap-near", -55.0)]
    t = analyze_topology(["192.168.1.1", "8.8.8.8"], "8.8.4.4", "HOME_5", "ap-far", -70.0, scan,
                         wired=False)
    assert t.is_mesh and t.ap_count == 2
    assert t.stuck_on_far_ap


def test_not_stuck_when_on_the_strongest_ap() -> None:
    scan = [("HOME_5", "ap-near", -50.0), ("HOME_2.4", "ap-far", -75.0)]
    t = analyze_topology(["192.168.1.1", "8.8.8.8"], "8.8.4.4", "HOME_5", "ap-near", -50.0, scan,
                         wired=False)
    assert not t.stuck_on_far_ap

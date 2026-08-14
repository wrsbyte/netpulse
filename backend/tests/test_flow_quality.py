from netpulse.probes.flow_quality import parse_ss_ti

SS_TIN = """State Recv-Q Send-Q Local Address:Port Peer Address:Port
ESTAB 0      0      192.168.100.99:54321 140.82.113.25:443
\t cubic rto:236 rtt:33.5/4.2 cwnd:10 minrtt:31.2 retrans:0/3 delivery_rate 12.3Mbps
ESTAB 0      0      192.168.100.99:54322 192.168.100.1:53
\t cubic rtt:1.2/0.5 min_rtt:0.9 retrans:0/0 delivery_rate:8.0Mbps
"""


def test_parse_pairs_socket_with_tcp_info() -> None:
    socks = parse_ss_ti(SS_TIN)
    assert len(socks) == 2
    a = next(s for s in socks if s.peer_ip == "140.82.113.25")
    assert a.srtt == 33.5
    assert a.min_rtt == 31.2
    assert a.retrans == 3
    assert a.delivery_mbps == 12.3


def test_parse_handles_missing_fields() -> None:
    b = next(s for s in parse_ss_ti(SS_TIN) if s.peer_ip == "192.168.100.1")
    assert b.min_rtt == 0.9
    assert b.retrans == 0
    assert b.delivery_mbps == 8.0


def test_parse_empty_on_header_only() -> None:
    assert parse_ss_ti("State Recv-Q Send-Q Local Address:Port Peer Address:Port\n") == []

from netpulse.probes.flows import extract_remotes

# `ss -tan state established` output: the State column is dropped when filtering by state,
# so the peer address is the last column. Regression fixture for that exact layout.
SS_ESTABLISHED = """Recv-Q Send-Q Local Address:Port  Peer Address:Port Process
0      0      192.168.100.99:54321 140.82.113.25:443
0      0      192.168.100.99:54322 140.82.113.25:443
0      0      192.168.100.99:54323 8.8.8.8:443
0      0      192.168.100.99:54324 192.168.100.1:53
0      0      [::1]:54325          [::1]:631
"""


def test_extract_remotes_counts_public_peers() -> None:
    counts = extract_remotes(SS_ESTABLISHED)
    assert counts == {"140.82.113.25": 2, "8.8.8.8": 1}  # gateway + loopback excluded


def test_extract_remotes_empty_on_header_only() -> None:
    assert extract_remotes("Recv-Q Send-Q Local Address:Port Peer Address:Port\n") == {}

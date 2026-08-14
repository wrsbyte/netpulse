from netpulse.probes.flows import _cymru_query, extract_remotes

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


def test_cymru_query_v4_and_v6() -> None:
    assert _cymru_query("8.8.8.8") == "8.8.8.8.origin.asn.cymru.com"
    # v6 is nibble-reversed against origin6: 32 single-hex labels, low nibble first.
    q = _cymru_query("2001:db8::1")
    assert q.endswith(".origin6.asn.cymru.com")
    labels = q[: -len(".origin6.asn.cymru.com")].split(".")
    assert len(labels) == 32
    assert all(len(x) == 1 for x in labels)
    assert labels[0] == "1" and labels[-1] == "2"  # ...::1 reversed starts 1; 2001 ends 2

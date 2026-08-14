from netpulse.probes.anycast import classify, parse_trace

TRACE = """fl=123f456
h=1.1.1.1
ip=177.241.63.129
ts=1700000000.1
visit_scheme=https
colo=DFW
loc=MX
tls=TLSv1.3
"""


def test_parse_trace_reads_colo_and_loc() -> None:
    assert parse_trace(TRACE) == ("DFW", "MX")
    assert parse_trace("garbage\n") == (None, None)


def test_out_of_country_when_pop_abroad() -> None:
    # Mega Cable serving Cloudflare from Dallas to a Mexican client — the real finding.
    r = classify(100.0, "cloudflare", "1.1.1.1", "DFW", "MX")
    assert r.colo_country == "US"
    assert r.out_of_country is True


def test_in_country_pop_is_not_flagged() -> None:
    r = classify(100.0, "cloudflare", "1.1.1.1", "QRO", "MX")  # Querétaro, in Mexico
    assert r.colo_country == "MX"
    assert r.out_of_country is False


def test_unknown_airport_does_not_false_flag() -> None:
    r = classify(100.0, "cloudflare", "1.1.1.1", "ZZZ", "MX")
    assert r.colo_country is None
    assert r.out_of_country is False

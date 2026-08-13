from netpulse.probes.active import parse_cli, parse_ookla

# Ookla `speedtest -f json`: bandwidth in bytes/s, loaded latency under download/upload.
OOKLA = {
    "ping": {"latency": 12.0, "jitter": 1.5},
    "download": {"bandwidth": 12_500_000, "latency": {"iqm": 45.0}},  # 100 Mbps
    "upload": {"bandwidth": 2_500_000, "latency": {"iqm": 30.0}},  # 20 Mbps
}

# Python `speedtest-cli --json`: down/up already in bits/s, ping in ms, no loaded latency.
CLI = {"ping": 18.3, "download": 94_000_000.0, "upload": 11_000_000.0}


def test_parse_ookla_derives_bufferbloat() -> None:
    row = parse_ookla(OOKLA, 100.0)
    assert round(row.download_mbps) == 100
    assert round(row.upload_mbps) == 20
    assert row.idle_latency == 12.0
    assert row.bufferbloat_ms == 33.0  # loaded 45 - idle 12
    assert row.grade == "B"
    assert row.mos is not None


def test_parse_cli_has_no_bufferbloat() -> None:
    row = parse_cli(CLI, 100.0)
    assert round(row.download_mbps) == 94
    assert round(row.upload_mbps) == 11
    assert row.idle_latency == 18.3
    assert row.bufferbloat_ms is None
    assert row.grade is None
    assert row.mos is not None

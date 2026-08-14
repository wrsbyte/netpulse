import asyncio

import pytest

from netpulse import shell
from netpulse.probes import dns, ping, wifi_scan

PING_OK = """PING 1.1.1.1 (1.1.1.1) 56(84) bytes of data.

--- 1.1.1.1 ping statistics ---
4 packets transmitted, 4 received, 0% packet loss, time 603ms
rtt min/avg/max/mdev = 8.100/9.250/11.400/1.200 ms
"""

PING_LOSS = """PING 9.9.9.9 (9.9.9.9) 56(84) bytes of data.

--- 9.9.9.9 ping statistics ---
4 packets transmitted, 0 received, 100% packet loss, time 3050ms
"""

DIG_OK = """;; ->>HEADER<<- opcode: QUERY, status: NOERROR, id: 1
;; flags: qr rd ra; QUERY: 1, ANSWER: 2, AUTHORITY: 0, ADDITIONAL: 1
;; Query time: 12 msec
"""

DIG_FAIL = """;; ->>HEADER<<- opcode: QUERY, status: SERVFAIL, id: 1
;; flags: qr rd ra; QUERY: 1, ANSWER: 0, AUTHORITY: 0, ADDITIONAL: 1
"""


def _result(stdout: str, ok: bool = True) -> shell.Result:
    return shell.Result(ok=ok, code=0 if ok else 1, stdout=stdout, stderr="", timed_out=False)


async def test_ping_parse_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shell, "run", lambda *a, **k: _async(_result(PING_OK)))
    row = await ping.sample(100.0, "1.1.1.1")
    assert row.loss_pct == 0.0
    assert row.rtt_min == 8.1
    assert row.rtt_avg == 9.25
    assert row.rtt_max == 11.4
    assert row.jitter == 1.2


async def test_ping_parse_full_loss(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shell, "run", lambda *a, **k: _async(_result(PING_LOSS)))
    row = await ping.sample(100.0, "9.9.9.9")
    assert row.loss_pct == 100.0
    assert row.rtt_avg is None


async def test_dns_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shell, "run", lambda *a, **k: _async(_result(DIG_OK)))
    row = await dns.sample(100.0, "google.com", "1.1.1.1")
    assert row.ok is True
    assert row.query_ms == 12.0
    assert row.resolver == "1.1.1.1"


async def test_dns_servfail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shell, "run", lambda *a, **k: _async(_result(DIG_FAIL, ok=False)))
    row = await dns.sample(100.0, "google.com", "")
    assert row.ok is False
    assert row.resolver == "system"


def test_nmcli_terse_split_handles_escaped_colons() -> None:
    line = r"36:80:CASA:AA\:BB\:CC\:DD\:EE\:FF"
    assert wifi_scan._split_terse(line) == ["36", "80", "CASA", "AA:BB:CC:DD:EE:FF"]


async def _async(value: shell.Result) -> shell.Result:
    return value


def test_dns_dot_labels_resolver_and_uses_tls(monkeypatch) -> None:


    captured = {}

    async def fake_run(*args, timeout=4):  # noqa: ASYNC109
        captured["args"] = args

        class R:
            ok = True
            stdout = "ANSWER: 1\nQuery time: 20 msec"

        return R()

    monkeypatch.setattr(dns.shell, "run", fake_run)
    row = asyncio.run(dns.sample(1.0, "example.com", "9.9.9.9", tls=True))
    assert "+tls" in captured["args"]
    assert row.resolver == "9.9.9.9 (DoT)"
    assert row.ok is True and row.query_ms == 20.0

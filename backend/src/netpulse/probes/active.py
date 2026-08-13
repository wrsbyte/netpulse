"""Active bandwidth + bufferbloat probe.

Supports two speedtest CLIs: Ookla's ``speedtest`` (reports idle vs loaded latency, so we
derive a bufferbloat grade) and the Python ``speedtest-cli`` (down/up/idle ping only — no
loaded latency, so no bufferbloat). The backend is detected once and cached. Consumes data,
so the collector runs it on a long cadence (and on demand). Returns ``None`` when neither CLI
is present or the run fails.
"""

from __future__ import annotations

import json
from typing import Any

from netpulse import shell
from netpulse.db.models import ActiveTest
from netpulse.quality import bufferbloat_grade, mos

# (command args, kind) of the detected CLI; cached after the first detection.
_backend: tuple[list[str], str] | None = None
_detected = False


def parse_ookla(data: dict[str, Any], ts: float) -> ActiveTest:
    """Ookla ``speedtest -f json``: bandwidth in bytes/s, loaded latency in ``latency.iqm``."""
    idle = data["ping"]["latency"]
    down_lat = data["download"].get("latency", {}).get("iqm", idle)
    up_lat = data["upload"].get("latency", {}).get("iqm", idle)
    loaded = max(down_lat, up_lat)
    bloat, grade = bufferbloat_grade(idle, loaded)
    # MOS reflects a call held *while* other traffic runs: use the loaded latency and the
    # measured loss, not idle-with-zero-loss (which would contradict a bad bufferbloat grade).
    loss = float(data.get("packetLoss", 0.0) or 0.0)
    return ActiveTest(
        ts=ts,
        download_mbps=data["download"]["bandwidth"] * 8 / 1e6,
        upload_mbps=data["upload"]["bandwidth"] * 8 / 1e6,
        idle_latency=idle, down_latency=down_lat, up_latency=up_lat,
        bufferbloat_ms=bloat, grade=grade,
        mos=mos(loaded, data["ping"].get("jitter", 0.0), loss),
    )


def parse_cli(data: dict[str, Any], ts: float) -> ActiveTest:
    """Python ``speedtest-cli --json``: down/up in bits/s, ``ping`` in ms, no loaded latency."""
    idle = data["ping"]
    return ActiveTest(
        ts=ts,
        download_mbps=data["download"] / 1e6,
        upload_mbps=data["upload"] / 1e6,
        idle_latency=idle, down_latency=None, up_latency=None,
        bufferbloat_ms=None, grade=None,
        mos=mos(idle, 0.0, 0.0),
    )


async def _detect() -> tuple[list[str], str] | None:
    global _backend, _detected  # noqa: PLW0603 — one-time cached CLI detection
    if _detected:
        return _backend
    _detected = True
    if shell.have("speedtest"):
        ver = await shell.run("speedtest", "--version", timeout=5)
        if "Ookla" in ver.stdout:
            _backend = (["speedtest", "-f", "json", "--accept-license", "--accept-gdpr"], "ookla")
            return _backend
    if shell.have("speedtest-cli"):
        _backend = (["speedtest-cli", "--json", "--secure"], "cli")
    return _backend


async def sample(ts: float) -> ActiveTest | None:
    backend = await _detect()
    if backend is None:
        return None
    args, kind = backend
    res = await shell.run(*args, timeout=90)
    if not res.ok:
        return None
    try:
        data = json.loads(res.stdout)
    except json.JSONDecodeError:
        return None
    return parse_ookla(data, ts) if kind == "ookla" else parse_cli(data, ts)

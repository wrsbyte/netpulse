"""WiFi radio quality probe — signal, bitrate, retries, BSSID (roaming), noise.

Reads the associated link via ``iw dev <iface> link`` + ``station dump``, and the channel
noise floor via ``survey dump``. All optional fields: on Ethernet or when ``iw`` reports
nothing, returns ``None`` and the collector skips the row.
"""

from __future__ import annotations

import re

from netpulse import shell
from netpulse.db.models import WifiRaw

_SSID = re.compile(r"SSID:\s*(.+)")
_BSSID = re.compile(r"Connected to ([0-9a-f:]{17})")
_FREQ = re.compile(r"freq:\s*(\d+)")
_SIGNAL = re.compile(r"signal:\s*(-?\d+)")
_TX_BITRATE = re.compile(r"tx bitrate:\s*([\d.]+)")
_RX_BITRATE = re.compile(r"rx bitrate:\s*([\d.]+)")
_TX_PACKETS = re.compile(r"tx packets:\s*(\d+)")
_TX_RETRIES = re.compile(r"tx retries:\s*(\d+)")
_TX_FAILED = re.compile(r"tx failed:\s*(\d+)")
_WIDTH = re.compile(r"(\d+)MHz")  # from the VHT/HE bitrate line, e.g. "585.1 MBit/s ... 80MHz"
_NOISE = re.compile(r"\[in use\].*?noise:\s*(-?\d+)", re.DOTALL)
_IN_USE_BLOCK = re.compile(r"\[in use\](.*?)(?:frequency:|\Z)", re.DOTALL)
_ACTIVE = re.compile(r"channel active time:\s*(\d+)")
_BUSY = re.compile(r"channel busy time:\s*(\d+)")
_RECEIVE = re.compile(r"channel receive time:\s*(\d+)")
_TRANSMIT = re.compile(r"channel transmit time:\s*(\d+)")


def _airtime(survey: str) -> tuple[float | None, float | None]:
    """Channel occupancy from the in-use frequency's survey block: total busy%% and the share not
    accounted for by our own rx/tx (= neighbours). Cumulative counters, so the ratio is the average
    occupancy since the interface came up — enough to rank a channel as clear vs saturated."""
    block = _IN_USE_BLOCK.search(survey)
    if not block:
        return None, None
    text = block.group(1)
    active, busy = _i(_ACTIVE, text), _i(_BUSY, text)
    if not active or busy is None:
        return None, None
    rx = _i(_RECEIVE, text) or 0
    tx = _i(_TRANSMIT, text) or 0
    return 100 * busy / active, max(0.0, 100 * (busy - rx - tx) / active)


def _f(pattern: re.Pattern[str], text: str) -> float | None:
    m = pattern.search(text)
    return float(m.group(1)) if m else None


def _i(pattern: re.Pattern[str], text: str) -> int | None:
    m = pattern.search(text)
    return int(m.group(1)) if m else None


async def sample(ts: float, iface: str) -> WifiRaw | None:
    link = await shell.run("iw", "dev", iface, "link", timeout=4)
    if not link.ok or "Not connected" in link.stdout:
        return None
    station = await shell.run("iw", "dev", iface, "station", "dump", timeout=4)
    survey = await shell.run("iw", "dev", iface, "survey", "dump", timeout=4)
    power = await shell.run("iw", "dev", iface, "get", "power_save", timeout=4)
    power_save = "Power save: on" in power.stdout if power.ok else None

    ssid_m = _SSID.search(link.stdout)
    bssid_m = _BSSID.search(link.stdout)
    busy_pct, foreign_pct = _airtime(survey.stdout)
    return WifiRaw(
        ts=ts,
        ssid=ssid_m.group(1).strip() if ssid_m else None,
        bssid=bssid_m.group(1) if bssid_m else None,
        freq=_i(_FREQ, link.stdout),
        width_mhz=_i(_WIDTH, station.stdout),
        signal_dbm=_f(_SIGNAL, station.stdout),
        noise_dbm=_f(_NOISE, survey.stdout),
        airtime_busy_pct=busy_pct,
        airtime_foreign_pct=foreign_pct,
        tx_bitrate=_f(_TX_BITRATE, station.stdout),
        rx_bitrate=_f(_RX_BITRATE, station.stdout),
        tx_packets=_i(_TX_PACKETS, station.stdout),
        tx_retries=_i(_TX_RETRIES, station.stdout),
        tx_failed=_i(_TX_FAILED, station.stdout),
        power_save=power_save,
    )

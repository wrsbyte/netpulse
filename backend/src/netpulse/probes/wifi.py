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
_NOISE = re.compile(r"\[in use\].*?noise:\s*(-?\d+)", re.DOTALL)


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
    return WifiRaw(
        ts=ts,
        ssid=ssid_m.group(1).strip() if ssid_m else None,
        bssid=bssid_m.group(1) if bssid_m else None,
        freq=_i(_FREQ, link.stdout),
        signal_dbm=_f(_SIGNAL, station.stdout),
        noise_dbm=_f(_NOISE, survey.stdout),
        tx_bitrate=_f(_TX_BITRATE, station.stdout),
        rx_bitrate=_f(_RX_BITRATE, station.stdout),
        tx_packets=_i(_TX_PACKETS, station.stdout),
        tx_retries=_i(_TX_RETRIES, station.stdout),
        tx_failed=_i(_TX_FAILED, station.stdout),
        power_save=power_save,
    )

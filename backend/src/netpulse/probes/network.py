"""Current-network detection.

Fingerprints the network the PC is on so samples can be attributed to it. The key is built
from the **gateway MAC** (stable across DHCP lease changes) plus SSID/BSSID and interface;
wired links have no SSID. ``fingerprint`` is pure over its inputs — the raw command text is
gathered separately — so the key logic is unit-tested.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from netpulse import shell

_DEFAULT_ROUTE = re.compile(r"default via (\S+) dev (\S+)")
_NEIGH_MAC = re.compile(r"lladdr ([0-9a-f:]{17})")
_SSID = re.compile(r"SSID:\s*(.+)")
_BSSID = re.compile(r"Connected to ([0-9a-f:]{17})")


@dataclass(frozen=True, slots=True)
class Fingerprint:
    key: str
    interface: str | None
    gateway_ip: str | None
    gateway_mac: str | None
    ssid: str | None
    bssid: str | None


def build_key(gateway_mac: str | None, gateway_ip: str | None, ssid: str | None) -> str:
    """Stable identity: prefer the gateway MAC (survives IP changes), then SSID."""
    anchor = gateway_mac or gateway_ip or "unknown"
    return f"{anchor}|{ssid or 'wired'}"


async def detect() -> Fingerprint | None:
    route = await shell.run("ip", "route", "show", "default", timeout=4)
    m = _DEFAULT_ROUTE.search(route.stdout)
    if not m:
        return None  # no route = fully offline; don't invent a network
    gateway_ip, interface = m.group(1), m.group(2)

    neigh = await shell.run("ip", "neigh", "show", gateway_ip, timeout=4)
    mac_m = _NEIGH_MAC.search(neigh.stdout)
    gateway_mac = mac_m.group(1) if mac_m else None

    ssid = bssid = None
    link = await shell.run("iw", "dev", interface, "link", timeout=4)
    if link.ok and "Not connected" not in link.stdout:
        ssid_m = _SSID.search(link.stdout)
        bssid_m = _BSSID.search(link.stdout)
        ssid = ssid_m.group(1).strip() if ssid_m else None
        bssid = bssid_m.group(1) if bssid_m else None

    return Fingerprint(
        key=build_key(gateway_mac, gateway_ip, ssid),
        interface=interface, gateway_ip=gateway_ip, gateway_mac=gateway_mac,
        ssid=ssid, bssid=bssid,
    )

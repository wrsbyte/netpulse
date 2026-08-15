"""LAN-vs-WAN attribution — is the instability your WiFi/LAN, or the ISP past your gateway?

The primitive is the spread of RTT to your own gateway (first hop) vs end-to-end to the internet.
If the variance is already present at the gateway, it is born on the local medium (WiFi/LAN) and no
ISP action will fix it; if the gateway is steady but the path jitters, it appears past your gateway
(access/ISP) and is the evidence to take to them. This is the automatic form of the manual
gateway-vs-Google ping comparison. Pure and unit-tested.
"""

from __future__ import annotations

from dataclasses import dataclass

_JITTER_FLOOR_MS = 10.0  # below this spread nobody notices; don't attribute noise
_LOCAL_RATIO = 0.6  # gateway spread this fraction of end-to-end -> variance is born locally
_LOSS_FLOOR_PCT = 1.0  # below this loss is not worth attributing


@dataclass(frozen=True, slots=True)
class LocalVerdict:
    layer: str  # "local" (WiFi/LAN) | "access" (ISP/past-gateway) | "ok"
    gw_jitter_ms: float
    e2e_jitter_ms: float
    gw_loss_pct: float
    e2e_loss_pct: float


def attribute_local(
    gw_jitter_ms: float | None,
    e2e_jitter_ms: float | None,
    gw_loss_pct: float | None,
    e2e_loss_pct: float | None,
) -> LocalVerdict | None:
    """Needs both a gateway signal and an end-to-end signal. ``*_jitter_ms`` is a spread proxy
    (e.g. p95 - p50) per side. Returns None when the gateway was not measured (can't attribute)."""
    if gw_jitter_ms is None or e2e_jitter_ms is None:
        return None
    gw_loss, e2e_loss = gw_loss_pct or 0.0, e2e_loss_pct or 0.0
    local_jitter = (
        e2e_jitter_ms >= _JITTER_FLOOR_MS and gw_jitter_ms >= e2e_jitter_ms * _LOCAL_RATIO
    )
    local_loss = gw_loss >= _LOSS_FLOOR_PCT and gw_loss >= e2e_loss * _LOCAL_RATIO
    if local_jitter or local_loss:
        layer = "local"
    elif e2e_jitter_ms >= _JITTER_FLOOR_MS or e2e_loss >= _LOSS_FLOOR_PCT:
        layer = "access"
    else:
        layer = "ok"
    return LocalVerdict(layer, gw_jitter_ms, e2e_jitter_ms, gw_loss, e2e_loss)

"""Automatic loss attribution — where does the loss start, and whose fault is it?

Given the per-hop loss profile toward a target (from mtr history) plus the correlation between
end-to-end loss and WiFi TX-retries, decide the layer: WiFi radio, LAN/gateway, or the ISP
path. Pure and unit-tested. This is the core of turning measurements into a defensible cause.
"""

from __future__ import annotations

from dataclasses import dataclass

_LOSS_THRESHOLD = 5.0  # % — below this a hop's loss is treated as ICMP-deprioritization noise
_STRONG_CORR = 0.5


@dataclass(frozen=True, slots=True)
class HopStat:
    hop: int
    host: str | None
    loss_pct: float


@dataclass(frozen=True, slots=True)
class Attribution:
    layer: str  # "wifi-radio" | "lan-gateway" | "isp" | "internet" | "none"
    hop: int | None
    host: str | None
    confidence: str  # "low" | "medium" | "high"
    reason: str


def _first_persistent_loss(hops: list[HopStat]) -> HopStat | None:
    """First hop whose loss is real: it and the final hop both exceed the threshold.

    Loss shown at a single middle hop but not at the destination is an ICMP-rate-limit
    artifact, not a path problem — only end-to-end loss that *starts* at a hop counts.
    """
    if not hops:
        return None
    end_loss = hops[-1].loss_pct
    if end_loss < _LOSS_THRESHOLD:
        return None
    for hop in hops:
        if hop.loss_pct >= _LOSS_THRESHOLD:
            return hop
    return None


def attribute(
    hops: list[HopStat], loss_retry_corr: float | None, wifi_weak: bool
) -> Attribution:
    start = _first_persistent_loss(hops)
    if start is None:
        return Attribution("none", None, None, "high", "No sustained end-to-end loss on the path.")

    radio_signal = wifi_weak or (loss_retry_corr is not None and loss_retry_corr >= _STRONG_CORR)

    if start.hop <= 1:
        if radio_signal:
            return Attribution(
                "wifi-radio", start.hop, start.host, "high",
                "Loss begins at the first hop and tracks WiFi TX-retries / weak signal.",
            )
        return Attribution(
            "lan-gateway", start.hop, start.host, "medium",
            "Loss begins at the gateway but the WiFi radio looks clean.",
        )

    confidence = "high" if (loss_retry_corr is None or loss_retry_corr < _STRONG_CORR) else "medium"
    return Attribution(
        "isp", start.hop, start.host, confidence,
        f"Loss first appears at hop {start.hop} ({start.host or 'unknown'}), beyond your "
        "gateway — the ISP path.",
    )

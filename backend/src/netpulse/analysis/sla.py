"""SLA compliance — measured delivery vs the ISP contract.

Turns "we got ~190 Mbps and 99.4% uptime" into "you contracted 200 Mbps / 99.5% and received 95%
of down capacity and breached uptime" — the contractual line that carries weight in a dispute.
Pure and unit-tested; the query layer supplies the measured aggregates.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class SlaTargets:
    download_mbps: float | None = None
    upload_mbps: float | None = None
    uptime_pct: float | None = None
    latency_ms: float | None = None


@dataclass(frozen=True, slots=True)
class Measured:
    download_mbps: float | None = None
    upload_mbps: float | None = None
    uptime_pct: float | None = None
    latency_ms: float | None = None


@dataclass(frozen=True, slots=True)
class SlaLine:
    metric: str  # "Download" | "Upload" | "Uptime" | "Latency"
    contracted: float
    measured: float | None
    delivered_pct: float | None  # measured / contracted (or headroom for latency)
    meets: bool | None  # None = not measured yet


@dataclass(frozen=True, slots=True)
class SlaReport:
    configured: bool  # False when no contract is set
    lines: list[SlaLine] = field(default_factory=list)
    breaches: int = 0


def _capacity_line(metric: str, contracted: float | None, measured: float | None) -> SlaLine | None:
    if contracted is None:
        return None
    if measured is None:
        return SlaLine(metric, contracted, None, None, None)
    pct = round(100 * measured / contracted, 1) if contracted else None
    meets = measured >= 0.9 * contracted  # ISPs commonly commit to ~90% of the headline rate
    return SlaLine(metric, contracted, round(measured, 1), pct, meets)


def _uptime_line(contracted: float | None, measured: float | None) -> SlaLine | None:
    if contracted is None:
        return None
    if measured is None:
        return SlaLine("Uptime", contracted, None, None, None)
    m = round(measured, 3)
    return SlaLine("Uptime", contracted, m, m, measured >= contracted)


def _latency_line(contracted: float | None, measured: float | None) -> SlaLine | None:
    if contracted is None:
        return None
    if measured is None:
        return SlaLine("Latency", contracted, None, None, None)
    # lower is better: "delivered" = how far under the ceiling (100% = at ceiling)
    pct = round(100 * measured / contracted, 1) if contracted else None
    return SlaLine("Latency", contracted, round(measured, 1), pct, measured <= contracted)


def assess(targets: SlaTargets, measured: Measured) -> SlaReport:
    """Per-metric contract compliance. Capacity meets at >=90% of the headline rate; uptime and
    latency are hard thresholds (>= for uptime, <= for latency)."""
    lines = [
        line
        for line in (
            _capacity_line("Download", targets.download_mbps, measured.download_mbps),
            _capacity_line("Upload", targets.upload_mbps, measured.upload_mbps),
            _uptime_line(targets.uptime_pct, measured.uptime_pct),
            _latency_line(targets.latency_ms, measured.latency_ms),
        )
        if line is not None
    ]
    breaches = sum(1 for line in lines if line.meets is False)
    return SlaReport(configured=bool(lines), lines=lines, breaches=breaches)

"""Rules-based verdict — turns window statistics into ranked findings and a headline.

This is the M1 conclusion layer: deterministic rules over what we already store. `conclude`
is pure (takes a :class:`WindowStats`, returns a :class:`Verdict`) so it is fully unit-tested;
gathering the stats from the DB lives in the query layer. M2 refines attribution with
baselines and correlation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from netpulse.analysis.attribute import Attribution
from netpulse.analysis.score import HealthInputs, HealthScore, health

_SEVERITY_RANK = {"error": 0, "warning": 1, "info": 2, "ok": 3}
_WEAK_SIGNAL_DBM = -72.0
_LAYER_LABEL = {
    "wifi-radio": "your WiFi radio",
    "lan-gateway": "your router / LAN",
    "isp": "the ISP path",
    "internet": "the internet path",
}


@dataclass(frozen=True, slots=True)
class WindowStats:
    loss: float | None = None  # avg % loss, internet targets
    latency: float | None = None  # p95 RTT ms, internet targets
    jitter: float | None = None  # avg ms
    bufferbloat: float | None = None  # latest ms added under load
    availability: float | None = None  # % of window internet reachable
    outage_count: int = 0
    downtime_s: float = 0.0
    worst_outage_s: float | None = None
    worst_outage_cause: str | None = None  # "isp" | "wifi/lan"
    worst_target: tuple[str, float] | None = None  # (host, loss%)
    wifi_signal_avg: float | None = None
    wifi_retries_max: int | None = None
    dns_fail: int = 0
    dns_total: int = 0
    attribution: Attribution | None = None
    loss_retry_corr: float | None = None
    # (provider, colo airport, colo country) for CDNs served from an out-of-country POP.
    anycast_out: list[tuple[str, str, str]] = field(default_factory=list)
    window_label: str = ""


@dataclass(frozen=True, slots=True)
class Finding:
    severity: str  # error | warning | info | ok
    title: str
    detail: str


@dataclass(frozen=True, slots=True)
class Verdict:
    score: HealthScore
    headline: str
    findings: list[Finding] = field(default_factory=list)


def _wifi_healthy(stats: WindowStats) -> bool:
    weak = stats.wifi_signal_avg is not None and stats.wifi_signal_avg <= _WEAK_SIGNAL_DBM
    return not weak


def conclude(stats: WindowStats) -> Verdict:
    score = health(
        HealthInputs(
            loss=stats.loss, latency=stats.latency, jitter=stats.jitter,
            bufferbloat=stats.bufferbloat, availability=stats.availability,
        )
    )
    findings: list[Finding] = []

    if stats.attribution and stats.attribution.layer != "none":
        a = stats.attribution
        has_loss = stats.outage_count > 0 or (stats.loss or 0) >= 2
        findings.append(Finding(
            "error" if has_loss else "info",
            f"Loss localized to {_LAYER_LABEL.get(a.layer, a.layer)}",
            f"{a.reason} (confidence: {a.confidence}).",
        ))

    if stats.outage_count:
        cause = _attribute_outage(stats)
        pct = 100 - stats.availability if stats.availability is not None else None
        pct_txt = f"{pct:.1f}% of the window" if pct is not None else "part of the window"
        findings.append(Finding(
            "error",
            f"Internet unreachable {pct_txt}",
            f"{stats.outage_count} outage(s), {stats.downtime_s / 60:.1f} min total; "
            f"worst {(stats.worst_outage_s or 0) / 60:.1f} min. Attributed to {cause}.",
        ))

    if stats.latency is not None and stats.latency >= 100:
        findings.append(Finding(
            "warning" if stats.latency < 250 else "error",
            "High latency to the internet",
            f"p95 RTT {stats.latency:.0f} ms — pages and calls feel sluggish even when "
            "bandwidth looks fine.",
        ))

    if stats.worst_target and stats.worst_target[1] >= 2:
        host, loss = stats.worst_target
        findings.append(Finding(
            "warning" if loss < 20 else "error",
            f"Packet loss to {host}",
            f"{loss:.1f}% average loss — degrades calls and page loads.",
        ))

    if not _wifi_healthy(stats):
        findings.append(Finding(
            "warning",
            "Weak WiFi signal",
            f"Average {stats.wifi_signal_avg:.0f} dBm (≤ {_WEAK_SIGNAL_DBM:.0f} is weak); "
            "move closer or change channel.",
        ))

    for provider, colo, country in stats.anycast_out:
        findings.append(Finding(
            "info",
            f"{provider.title()} served from {colo} ({country})",
            "out-of-country POP — the ISP routes this CDN abroad instead of an in-country POP, "
            "adding international latency and loss. A different DNS/VPN may reach a closer POP.",
        ))

    if stats.dns_total:
        rate = 100 * stats.dns_fail / stats.dns_total
        if rate >= 2:  # a handful of timeouts is normal; only flag a real failure rate
            findings.append(Finding(
                "warning" if rate < 10 else "error",
                "DNS failures",
                f"{stats.dns_fail}/{stats.dns_total} lookups failed ({rate:.1f}%).",
            ))

    if not findings:
        findings.append(Finding("ok", "Network healthy", "No outages, loss or DNS issues."))

    findings.sort(key=lambda f: _SEVERITY_RANK[f.severity])
    return Verdict(score=score, headline=_headline(score, stats, findings), findings=findings)


def _attribute_outage(stats: WindowStats) -> str:
    if stats.attribution and stats.attribution.layer != "none":
        return _LAYER_LABEL.get(stats.attribution.layer, stats.attribution.layer)
    if stats.worst_outage_cause == "wifi/lan" or not _wifi_healthy(stats):
        return "your WiFi / local link"
    if stats.worst_outage_cause == "isp":
        return "the ISP path (loss beyond the gateway)"
    return "the internet path"


def _headline(score: HealthScore, stats: WindowStats, findings: list[Finding]) -> str:
    top = findings[0]
    if top.severity == "ok":
        return f"Grade {score.grade} — your internet was healthy {stats.window_label}".strip()
    return f"Grade {score.grade} — {top.title.lower()} {stats.window_label}".strip()

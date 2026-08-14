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
from netpulse.analysis.segment import SegmentVerdict
from netpulse.analysis.wifi_channel import ChannelAdvice

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
    loss: float | None = None  # worst path p95 % loss, internet targets
    loss_ci: tuple[float, float] | None = None  # block-bootstrap 95% CI on worst-path loss
    loss_burst_len: float | None = None  # mean consecutive lossy cycles (bursty vs uniform)
    latency: float | None = None  # p95 RTT ms, internet targets
    latency_excess: float | None = None  # p95 RTT above the path's own empirical floor
    jitter: float | None = None  # p95 ms
    bufferbloat: float | None = None  # latest ms added under load
    availability: float | None = None  # % of window internet reachable
    outage_count: int = 0
    downtime_s: float = 0.0
    worst_outage_s: float | None = None
    worst_outage_cause: str | None = None  # "isp" | "wifi/lan"
    worst_target: tuple[str, float] | None = None  # (host, loss%)
    wifi_signal_avg: float | None = None
    wifi_retries_max: int | None = None
    wifi_power_save: bool | None = None
    channel_advice: ChannelAdvice | None = None
    outages_client_initiated: int = 0  # of outage_count, how many were the laptop disconnecting
    dns_fail: int = 0
    dns_total: int = 0
    attribution: Attribution | None = None
    segment: SegmentVerdict | None = None
    loss_retry_corr: float | None = None
    # (provider, colo airport, colo country) for CDNs served from an out-of-country POP.
    anycast_out: list[tuple[str, str, str]] = field(default_factory=list)
    regional_pct: float | None = None  # percentile of your core-net latency within the region
    regional_user_rtt: float | None = None
    bgp_updates: int | None = None  # recent BGP updates to your prefix (route-stability)
    bgp_stable: bool | None = None
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

    if stats.outage_count and stats.outages_client_initiated >= stats.outage_count:
        findings.append(Finding(
            "info",
            "Brief WiFi drops were your laptop, not the network",
            f"{stats.outages_client_initiated} disconnect(s) were client-initiated "
            "(suspend / lid-close / power-save), not a network outage.",
        ))
    elif stats.outage_count:
        cause = _attribute_outage(stats)
        pct = 100 - stats.availability if stats.availability is not None else None
        pct_txt = f"{pct:.1f}% of the window" if pct is not None else "part of the window"
        client_txt = (
            f" ({stats.outages_client_initiated} were your laptop suspending, not the network)"
            if stats.outages_client_initiated
            else ""
        )
        findings.append(Finding(
            "error",
            f"Internet unreachable {pct_txt}",
            f"{stats.outage_count} outage(s), {stats.downtime_s / 60:.1f} min total; "
            f"worst {(stats.worst_outage_s or 0) / 60:.1f} min. Attributed to {cause}{client_txt}.",
        ))

    if stats.latency is not None and stats.latency >= 100:
        excess = stats.latency_excess
        excess_txt = (
            f" ({excess:.0f} ms above the path's own minimum — congestion, not distance)"
            if excess is not None and excess >= 20
            else ""
        )
        findings.append(Finding(
            "warning" if stats.latency < 250 else "error",
            "High latency to the internet",
            f"p95 RTT {stats.latency:.0f} ms{excess_txt} — pages and calls feel sluggish.",
        ))

    if stats.worst_target and stats.worst_target[1] >= 2:
        host, loss = stats.worst_target
        ci_txt = ""
        if stats.loss_ci:
            ci_txt = f" (95% CI {stats.loss_ci[0]:.1f}-{stats.loss_ci[1]:.1f}%)"
        burst_txt = (
            f", in bursts of ~{stats.loss_burst_len:.0f} cycles"
            if stats.loss_burst_len and stats.loss_burst_len >= 2
            else ""
        )
        findings.append(Finding(
            "warning" if loss < 20 else "error",
            f"Packet loss to {host}",
            f"{loss:.1f}% average loss{ci_txt}{burst_txt} — degrades calls and page loads.",
        ))

    if not _wifi_healthy(stats):
        findings.append(Finding(
            "warning",
            "Weak WiFi signal",
            f"Average {stats.wifi_signal_avg:.0f} dBm (≤ {_WEAK_SIGNAL_DBM:.0f} is weak); "
            "move closer or change channel.",
        ))

    if stats.wifi_power_save:
        findings.append(Finding(
            "warning",
            "WiFi power-save is on",
            "the adapter's power-saving causes beacon loss and brief drops; disable it "
            "(NetworkManager wifi.powersave = 2).",
        ))

    ca = stats.channel_advice
    if ca and ca.crowded and ca.best_alternative is not None:
        findings.append(Finding(
            "warning",
            f"WiFi channel {ca.current} is crowded",
            f"{ca.aps_on_current} APs share your 5 GHz channel; switch the router to channel "
            f"{ca.best_alternative} ({ca.alternative_aps} APs, no DFS).",
        ))

    findings.extend(_route_context_findings(stats))

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


def _route_context_findings(stats: WindowStats) -> list[Finding]:
    """Non-severity route/region context: where latency accrues, out-of-country POPs, and how
    the connection ranks regionally. Extracted to keep `conclude` legible."""
    out: list[Finding] = []
    seg = stats.segment
    if seg and seg.layer == "transit" and seg.transit_ms and seg.local_rtt is not None:
        out.append(Finding(
            "info", "Latency is beyond your ISP, in transit",
            f"your best-peered path is {seg.local_rtt:.0f} ms (access is fine) but the degraded "
            f"path adds ~{seg.transit_ms:.0f} ms of transit — international routing, not your "
            "zone; a VPN may route around it.",
        ))
    elif seg and seg.layer == "access" and seg.local_rtt is not None:
        out.append(Finding(
            "warning", "Your ISP's access network is slow",
            f"even your best-peered path is {seg.local_rtt:.0f} ms — the ISP access/backhaul "
            "itself is heavy, an operator/local-capacity issue a VPN won't fix.",
        ))

    for provider, colo, country in stats.anycast_out:
        out.append(Finding(
            "info", f"{provider.title()} served from {colo} ({country})",
            "out-of-country POP — the ISP routes this CDN abroad instead of an in-country POP, "
            "adding international latency and loss. A different DNS/VPN may reach a closer POP.",
        ))

    if stats.regional_pct is not None and stats.regional_user_rtt is not None:
        if stats.regional_pct <= 40:
            note = "better than most connections in your region"
        elif stats.regional_pct <= 70:
            note = "typical for your region"
        else:
            note = "worse than most connections in your region"
        out.append(Finding(
            "info", "Regional context (RIPE Atlas)",
            f"your latency to core internet infrastructure ({stats.regional_user_rtt:.0f} ms) is "
            f"at the {stats.regional_pct:.0f}th percentile of your country's probes — {note}.",
        ))

    if stats.bgp_updates is not None and stats.bgp_stable is False:
        out.append(Finding(
            "info", "Unstable BGP route",
            f"your prefix saw {stats.bgp_updates} BGP updates recently — the global route to you "
            "is flapping (RIPEstat), which adds latency/loss on top of any congestion.",
        ))
    return out


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

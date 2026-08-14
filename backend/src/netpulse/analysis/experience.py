"""What the connection feels like for real activities.

Translates the raw metrics we already measure (RTT, loss, jitter, bufferbloat, capacity, DNS) into
a plain-language rating per activity — calls, browsing, streaming, gaming — each with the technical
numbers that drove it. Pure and unit-tested: the query layer gathers the inputs, this decides.
"""

from __future__ import annotations

from dataclasses import dataclass, field

_RATING_RANK = {"poor": 0, "fair": 1, "good": 2, "unknown": 3}


@dataclass(frozen=True, slots=True)
class ExperienceInputs:
    rtt_ms: float | None = None  # typical RTT to the internet (p50)
    loss_pct: float | None = None  # typical end-to-end loss
    jitter_ms: float | None = None  # p95 RTT variation
    bufferbloat_ms: float | None = None  # latency added under load (latest speedtest)
    download_mbps: float | None = None  # last measured capacity
    upload_mbps: float | None = None
    dns_ms: float | None = None  # median resolver time


@dataclass(frozen=True, slots=True)
class Metric:
    label: str
    value: float | None
    unit: str
    ok: bool  # within the good range for this activity


@dataclass(frozen=True, slots=True)
class ActivityVerdict:
    activity: str  # "Video calls" | "Browsing" | "Streaming" | "Gaming"
    rating: str  # "good" | "fair" | "poor" | "unknown"
    summary: str  # one plain-language line
    metrics: list[Metric] = field(default_factory=list)


def _rate(good: bool, fair: bool) -> str:
    if good:
        return "good"
    if fair:
        return "fair"
    return "poor"


def _known(*values: float | None) -> bool:
    return any(v is not None for v in values)


def _m(label: str, value: float | None, unit: str, good_below: float) -> Metric:
    return Metric(label, value, unit, value is not None and value <= good_below)


def _calls(i: ExperienceInputs) -> ActivityVerdict:
    # Calls die from jitter, loss and latency-under-load, not from raw bandwidth.
    metrics = [
        _m("Latency under load", i.bufferbloat_ms, "ms", 30),
        _m("Jitter", i.jitter_ms, "ms", 15),
        _m("Loss", i.loss_pct, "%", 1),
    ]
    if not _known(i.bufferbloat_ms, i.jitter_ms, i.loss_pct):
        return ActivityVerdict("Video calls", "unknown", "Not enough data yet.", metrics)
    good = all(m.ok for m in metrics if m.value is not None)
    fair = (i.loss_pct or 0) < 3 and (i.bufferbloat_ms or 0) < 80 and (i.jitter_ms or 0) < 30
    rating = _rate(good, fair)
    summary = {
        "good": "Calls should be clear and stable.",
        "fair": "Calls usable but may glitch under load or on jitter.",
        "poor": "Calls likely to freeze, drop audio or lag.",
    }[rating]
    return ActivityVerdict("Video calls", rating, summary, metrics)


def _browsing(i: ExperienceInputs) -> ActivityVerdict:
    metrics = [
        _m("Latency", i.rtt_ms, "ms", 80),
        _m("DNS lookup", i.dns_ms, "ms", 50),
        _m("Loss", i.loss_pct, "%", 2),
    ]
    if not _known(i.rtt_ms, i.dns_ms):
        return ActivityVerdict("Browsing", "unknown", "Not enough data yet.", metrics)
    good = all(m.ok for m in metrics if m.value is not None)
    fair = (i.rtt_ms or 0) < 150 and (i.dns_ms or 0) < 120
    rating = _rate(good, fair)
    summary = {
        "good": "Pages open instantly.",
        "fair": "Pages open with a slight lag.",
        "poor": "Pages feel sluggish or stall while loading.",
    }[rating]
    return ActivityVerdict("Browsing", rating, summary, metrics)


def _streaming(i: ExperienceInputs) -> ActivityVerdict:
    # Streaming buffers absorb latency; what matters is enough capacity and low sustained loss.
    metrics = [
        Metric("Download", i.download_mbps, "Mbps", (i.download_mbps or 0) >= 25),
        _m("Loss", i.loss_pct, "%", 2),
    ]
    if not _known(i.download_mbps):
        return ActivityVerdict("Streaming", "unknown", "Run a speedtest to assess.", metrics)
    good = (i.download_mbps or 0) >= 25 and (i.loss_pct or 0) < 2
    fair = (i.download_mbps or 0) >= 5 and (i.loss_pct or 0) < 5
    rating = _rate(good, fair)
    summary = {
        "good": "4K/HD streaming without buffering.",
        "fair": "HD works; 4K may buffer at peak.",
        "poor": "Expect buffering or quality drops.",
    }[rating]
    return ActivityVerdict("Streaming", rating, summary, metrics)


def _gaming(i: ExperienceInputs) -> ActivityVerdict:
    metrics = [
        _m("Latency", i.rtt_ms, "ms", 80),
        _m("Jitter", i.jitter_ms, "ms", 10),
        _m("Loss", i.loss_pct, "%", 1),
    ]
    if not _known(i.rtt_ms, i.jitter_ms, i.loss_pct):
        return ActivityVerdict("Gaming", "unknown", "Not enough data yet.", metrics)
    good = all(m.ok for m in metrics if m.value is not None)
    fair = (i.rtt_ms or 0) < 120 and (i.jitter_ms or 0) < 25 and (i.loss_pct or 0) < 3
    rating = _rate(good, fair)
    summary = {
        "good": "Responsive; no rubber-banding.",
        "fair": "Playable but you may feel lag spikes.",
        "poor": "Lag and rubber-banding likely.",
    }[rating]
    return ActivityVerdict("Gaming", rating, summary, metrics)


def assess(i: ExperienceInputs) -> list[ActivityVerdict]:
    """Rate every activity, worst first — the poor ones are what the user should act on."""
    verdicts = [_calls(i), _browsing(i), _streaming(i), _gaming(i)]
    verdicts.sort(key=lambda v: _RATING_RANK[v.rating])
    return verdicts

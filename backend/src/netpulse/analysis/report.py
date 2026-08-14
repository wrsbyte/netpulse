"""Forensic evidence report — a self-contained, timestamped HTML document composing the verdict,
SLA compliance, outage log, DNS comparison and geolocated route into one printable artifact you can
hand to an ISP. The HTML builder is pure (takes a context dataclass) so it is unit-tested; the
router gathers the data. No external assets — inline CSS, print-to-PDF friendly.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ReportRow:
    label: str
    value: str


@dataclass(frozen=True, slots=True)
class ReportSection:
    title: str
    rows: list[ReportRow] = field(default_factory=list)
    note: str = ""


@dataclass(frozen=True, slots=True)
class ReportContext:
    generated_at: str  # human date (stamped by the caller — no clock in this module)
    network_label: str
    window_label: str
    grade: str
    headline: str
    sections: list[ReportSection] = field(default_factory=list)
    methodology: str = ""


_CSS = """
body{font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;color:#111;max-width:820px;
margin:2rem auto;padding:0 1rem}h1{font-size:1.5rem;margin:0}h2{font-size:1.05rem;border-bottom:1px
solid #ddd;padding-bottom:.2rem;margin-top:1.6rem}.meta{color:#666;font-size:.85rem}.grade{display:
inline-block;font-weight:700;padding:.15rem .5rem;border-radius:.4rem;border:1px solid #ccc}
table{border-collapse:collapse;width:100%;margin-top:.4rem}td{padding:.25rem .5rem;border-bottom:1px
solid #eee}td:first-child{color:#555;width:40%}.note{color:#666;font-size:.85rem;margin-top:.3rem}
.method{color:#555;font-size:.8rem;white-space:pre-wrap;margin-top:.5rem}
@media print{body{margin:0}}
"""


def _esc(s: str) -> str:
    return html.escape(str(s))


def build_report_html(ctx: ReportContext) -> str:
    """Render the context into a standalone HTML document (inline CSS, no external requests)."""
    parts = [
        "<!doctype html><meta charset='utf-8'>",
        f"<title>netpulse report — {_esc(ctx.network_label)}</title>",
        f"<style>{_CSS}</style>",
        "<h1>netpulse — network evidence report</h1>",
        f"<div class='meta'>Network: {_esc(ctx.network_label)} · Window: {_esc(ctx.window_label)}"
        f" · Generated: {_esc(ctx.generated_at)}</div>",
        f"<p><span class='grade'>Grade {_esc(ctx.grade)}</span> &nbsp; {_esc(ctx.headline)}</p>",
    ]
    for sec in ctx.sections:
        parts.append(f"<h2>{_esc(sec.title)}</h2>")
        if sec.rows:
            parts.append("<table>")
            parts.extend(
                f"<tr><td>{_esc(r.label)}</td><td>{_esc(r.value)}</td></tr>" for r in sec.rows
            )
            parts.append("</table>")
        if sec.note:
            parts.append(f"<div class='note'>{_esc(sec.note)}</div>")
    if ctx.methodology:
        parts.append("<h2>Methodology</h2>")
        parts.append(f"<div class='method'>{_esc(ctx.methodology)}</div>")
    return "".join(parts)


METHODOLOGY = (
    "Measurements are taken continuously on the client host: ICMP latency/loss every ~3 s to "
    "multiple internet targets, DNS resolution timing per resolver, passive TCP transport quality "
    "(ss -ti), periodic speed/bufferbloat tests, and per-hop traceroutes geolocated via RIPEstat.\n"
    "Latency/loss are reported per-target then aggregated to a representative median so a single "
    "distant or badly-peered host does not skew the result. Samples taken during the tool's own "
    "WiFi scans and speedtests are excluded. Availability is computed over actually-sampled time "
    "(collection gaps from device sleep are excluded, not counted as uptime). Loss shown at an "
    "intermediate traceroute hop is treated as ICMP rate-limiting unless it persists to the "
    "destination. Figures carry the window they were measured over."
)

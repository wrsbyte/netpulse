"""Evidence report endpoint — composes the current analysis into a standalone printable HTML doc."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from netpulse.analysis.report import (
    METHODOLOGY,
    ReportContext,
    ReportRow,
    ReportSection,
    build_report_html,
)
from netpulse.analysis.verdict import conclude
from netpulse.api import queries
from netpulse.api.deps import db, resolve_network, window_for

router = APIRouter(prefix="/api", tags=["report"])
Db = Annotated[Session, Depends(db)]
_LABEL = {"6h": "the last 6 hours", "24h": "the last 24 hours", "7d": "the last 7 days"}


def _network_label(session: Session, network_id: int | None) -> str:
    if network_id is None:
        return "all networks"
    net = next((n for n in queries.networks(session) if n.id == network_id), None)
    return (net.label or net.ssid or f"network {network_id}") if net else f"network {network_id}"


@router.get("/report", response_class=HTMLResponse)
def get_report(
    session: Db,
    range: Annotated[str, Query()] = "24h",
    network: Annotated[str, Query()] = "current",
) -> HTMLResponse:
    _, window = window_for(range)
    nid = resolve_network(session, network)
    label = _LABEL.get(range, range)
    verdict = conclude(queries.gather_stats(session, window, f"in {label}", nid))
    sla = queries.sla(session, window, label, nid)
    dns = queries.dns_compare(session, window, nid)
    outages = [e for e in queries.events(session, window, nid) if e.kind == "outage"]
    _, path = queries._hop_path(session, nid)

    sections = [
        ReportSection(
            "Findings",
            [ReportRow(f.severity.upper(), f"{f.title}. {f.detail}") for f in verdict.findings],
        ),
        ReportSection(
            "Health score (0-100, higher is better)",
            [ReportRow(k, str(round(v))) for k, v in verdict.score.breakdown.items()],
        ),
    ]
    if sla.configured:
        sections.append(ReportSection(
            "Contract vs delivered (SLA)",
            [
                ReportRow(
                    line.metric,
                    f"contracted {line.contracted}, measured "
                    f"{line.measured if line.measured is not None else 'n/a'}"
                    f" — {'MET' if line.meets else 'BREACH' if line.meets is False else 'pending'}",
                )
                for line in sla.lines
            ],
            note=f"{sla.breaches} contracted metric(s) below what is paid for."
            if sla.breaches
            else "",
        ))
    sections.append(ReportSection(
        "Outages",
        [
            ReportRow(
                datetime.fromtimestamp(o.ts, UTC).astimezone().strftime("%Y-%m-%d %H:%M"),
                f"{round(o.duration or 0)} s — {o.detail}",
            )
            for o in outages
        ],
        note="No outages recorded in the window." if not outages else "",
    ))
    def _ms(v: float | None) -> str:
        return f"{round(v)} ms" if v is not None else "n/a"

    sections.append(ReportSection(
        "DNS resolvers",
        [
            ReportRow(
                d.resolver,
                f"median {_ms(d.median_ms)}, p95 {_ms(d.p95_ms)}, jitter {_ms(d.jitter_ms)}, "
                f"failures {d.fail_pct}% (n={d.n})",
            )
            for d in dns
        ],
    ))
    if path:
        sections.append(ReportSection(
            "Geolocated route (primary target)",
            [
                ReportRow(
                    f"hop {h.hop} — {h.city or h.country or h.ip}",
                    f"{round(h.rtt_ms) if h.rtt_ms is not None else '?'} ms"
                    + (f", loss {h.loss_pct}%" if h.loss_pct else ""),
                )
                for h in path
            ],
        ))

    ctx = ReportContext(
        generated_at=datetime.fromtimestamp(time.time(), UTC).astimezone().strftime(
            "%Y-%m-%d %H:%M %Z"
        ),
        network_label=_network_label(session, nid),
        window_label=label,
        grade=verdict.score.grade,
        # the badge already shows "Grade X"; drop that prefix from the headline to avoid printing it
        # twice, and keep just the human sentence.
        headline=verdict.headline.split(" — ", 1)[-1].capitalize(),
        sections=sections,
        methodology=METHODOLOGY,
    )
    return HTMLResponse(build_report_html(ctx))

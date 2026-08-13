"""Read endpoints — series, active tests, events, flows, status, networks, verdict.

Every data endpoint takes ``network``: ``current`` (default — the network in use now),
``all`` (every network combined), or a numeric id. This keeps analysis scoped to one network
as the PC moves between home / office / café.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from netpulse.aggregation import SOURCES
from netpulse.analysis.verdict import Verdict, conclude
from netpulse.api import queries
from netpulse.api.deps import RANGES, db
from netpulse.api.schemas import (
    ActivePoint,
    EventOut,
    FindingOut,
    FlowOut,
    NetworkOut,
    ScoreOut,
    SeriesResponse,
    Status,
    VerdictOut,
)
from netpulse.config import get_config

router = APIRouter(prefix="/api", tags=["data"])

_METRICS = {s.name for s in SOURCES}
_RANGE_LABEL = {"6h": "in the last 6h", "24h": "in the last 24h", "7d": "in the last 7 days"}
Db = Annotated[Session, Depends(db)]


def _window(range_key: str) -> tuple[str, int]:
    if range_key not in RANGES:
        raise HTTPException(400, f"range must be one of {list(RANGES)}")
    return RANGES[range_key]


def _resolve_network(session: Session, network: str) -> int | None:
    if network == "all":
        return None
    if network == "current":
        return queries.current_network_id(session)
    try:
        return int(network)
    except ValueError:
        raise HTTPException(400, "network must be 'current', 'all', or a numeric id") from None


@router.get("/series", response_model=SeriesResponse)
def get_series(
    session: Db,
    metric: Annotated[str, Query()],
    range: Annotated[str, Query()] = "6h",
    network: Annotated[str, Query()] = "current",
) -> SeriesResponse:
    if metric not in _METRICS:
        raise HTTPException(400, f"unknown metric; known: {sorted(_METRICS)}")
    resolution, window = _window(range)
    return queries.series(
        session, metric, range, resolution, window,
        network_id=_resolve_network(session, network),
    )


@router.get("/active", response_model=list[ActivePoint])
def get_active(
    session: Db,
    range: Annotated[str, Query()] = "24h",
    network: Annotated[str, Query()] = "current",
) -> list[ActivePoint]:
    _, window = _window(range)
    return queries.active_tests(session, window, _resolve_network(session, network))


@router.get("/events", response_model=list[EventOut])
def get_events(
    session: Db,
    range: Annotated[str, Query()] = "24h",
    network: Annotated[str, Query()] = "current",
) -> list[EventOut]:
    _, window = _window(range)
    return queries.events(session, window, _resolve_network(session, network))


@router.get("/flows", response_model=list[FlowOut])
def get_flows(
    session: Db,
    range: Annotated[str, Query()] = "6h",
    network: Annotated[str, Query()] = "current",
) -> list[FlowOut]:
    _, window = _window(range)
    return queries.top_flows(session, window, _resolve_network(session, network))


@router.get("/status", response_model=Status)
def get_status(
    session: Db,
    range: Annotated[str, Query()] = "24h",
    network: Annotated[str, Query()] = "current",
) -> Status:
    _, window = _window(range)
    return queries.status(session, window, get_config().interface or "auto",
                          _resolve_network(session, network))


@router.get("/networks", response_model=list[NetworkOut])
def get_networks(session: Db) -> list[NetworkOut]:
    return queries.networks(session)


@router.get("/verdict", response_model=VerdictOut)
def get_verdict(
    session: Db,
    range: Annotated[str, Query()] = "24h",
    network: Annotated[str, Query()] = "current",
) -> VerdictOut:
    _, window = _window(range)
    stats = queries.gather_stats(
        session, window, _RANGE_LABEL.get(range, ""), _resolve_network(session, network)
    )
    return to_verdict_out(conclude(stats))


def to_verdict_out(verdict: Verdict) -> VerdictOut:
    # asdict (not vars): Verdict's members are slotted dataclasses with no __dict__.
    return VerdictOut(
        score=ScoreOut(**asdict(verdict.score)),
        headline=verdict.headline,
        findings=[FindingOut(**asdict(f)) for f in verdict.findings],
    )


@router.get("/metrics", response_model=list[str])
def list_metrics() -> list[str]:
    return sorted(_METRICS)

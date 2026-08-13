"""Read endpoints — series, active tests, events, flows, status."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from netpulse.aggregation import SOURCES
from netpulse.api import queries
from netpulse.api.deps import RANGES, db
from netpulse.api.schemas import (
    ActivePoint,
    EventOut,
    FlowOut,
    SeriesResponse,
    Status,
)
from netpulse.config import get_config

router = APIRouter(prefix="/api", tags=["data"])

_METRICS = {s.name for s in SOURCES}
Db = Annotated[Session, Depends(db)]


def _window(range_key: str) -> tuple[str, int]:
    if range_key not in RANGES:
        raise HTTPException(400, f"range must be one of {list(RANGES)}")
    return RANGES[range_key]


@router.get("/series", response_model=SeriesResponse)
def get_series(
    session: Db,
    metric: Annotated[str, Query()],
    range: Annotated[str, Query()] = "6h",
) -> SeriesResponse:
    if metric not in _METRICS:
        raise HTTPException(400, f"unknown metric; known: {sorted(_METRICS)}")
    resolution, window = _window(range)
    return queries.series(session, metric, range, resolution, window)


@router.get("/active", response_model=list[ActivePoint])
def get_active(session: Db, range: Annotated[str, Query()] = "24h") -> list[ActivePoint]:
    _, window = _window(range)
    return queries.active_tests(session, window)


@router.get("/events", response_model=list[EventOut])
def get_events(session: Db, range: Annotated[str, Query()] = "24h") -> list[EventOut]:
    _, window = _window(range)
    return queries.events(session, window)


@router.get("/flows", response_model=list[FlowOut])
def get_flows(session: Db, range: Annotated[str, Query()] = "6h") -> list[FlowOut]:
    _, window = _window(range)
    return queries.top_flows(session, window)


@router.get("/status", response_model=Status)
def get_status(session: Db, range: Annotated[str, Query()] = "24h") -> Status:
    _, window = _window(range)
    return queries.status(session, window, get_config().interface or "auto")


@router.get("/metrics", response_model=list[str])
def list_metrics() -> list[str]:
    return sorted(_METRICS)

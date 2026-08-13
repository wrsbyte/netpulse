"""Raw-data endpoints — a real data explorer: filter, sort, aggregate, paginate, export.

Exposes the append-only sample tables with an explicit, typed column allow-list (no reflection).
Filtering, sorting and aggregation all run server-side over the full window so they act on the
whole dataset, not just the visible page (see docs/PRODUCT_CONVENTIONS.md).
"""

from __future__ import annotations

import csv
import io
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from netpulse.api import queries
from netpulse.api.deps import db, resolve_network, window_for
from netpulse.api.queries import ColSpec, RawQuery
from netpulse.api.schemas import RawPage
from netpulse.db.models import DnsRaw, Event, Flow, PingRaw, Traceroute

router = APIRouter(prefix="/api/raw", tags=["raw"])
Db = Annotated[Session, Depends(db)]

_MS = "ms"
_PCT = "%"

# name -> (model, ordered typed column specs). Explicit allow-list.
_TABLES: dict[str, tuple[type, list[ColSpec]]] = {
    "ping": (PingRaw, [
        ColSpec("ts", "time"),
        ColSpec("target", "string", enum=True),
        ColSpec("loss_pct", "number", _PCT),
        ColSpec("rtt_avg", "number", _MS),
        ColSpec("rtt_min", "number", _MS),
        ColSpec("rtt_max", "number", _MS),
        ColSpec("jitter", "number", _MS),
    ]),
    "dns": (DnsRaw, [
        ColSpec("ts", "time"),
        ColSpec("domain", "string", enum=True),
        ColSpec("resolver", "string", enum=True),
        ColSpec("query_ms", "number", _MS),
        ColSpec("ok", "bool"),
    ]),
    "flows": (Flow, [
        ColSpec("ts", "time"),
        ColSpec("remote_ip", "string"),
        ColSpec("app", "string", enum=True),
        ColSpec("rdns", "string"),
        ColSpec("asn", "string"),
        ColSpec("conns", "number", "count"),
    ]),
    "traceroute": (Traceroute, [
        ColSpec("ts", "time"),
        ColSpec("target", "string", enum=True),
        ColSpec("hop", "number", "#"),
        ColSpec("host", "string"),
        ColSpec("loss_pct", "number", _PCT),
        ColSpec("rtt_ms", "number", _MS),
    ]),
    "events": (Event, [
        ColSpec("ts", "time"),
        ColSpec("end_ts", "time"),
        ColSpec("kind", "string", enum=True),
        ColSpec("severity", "string", enum=True),
        ColSpec("detail", "string"),
    ]),
}

_EXPORT_CAP = 50_000


def _table(name: str) -> tuple[type, list[ColSpec]]:
    if name not in _TABLES:
        raise HTTPException(404, f"unknown table; known: {sorted(_TABLES)}")
    return _TABLES[name]


def _parse_filters(pairs: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for pair in pairs:
        col, sep, val = pair.partition(":")
        if sep:
            out[col] = val
    return out


def _query(
    session: Session, name: str, range: str, network: str,
    q: str | None, sort: str | None, dir: str, f: list[str],
) -> tuple[type, list[ColSpec], RawQuery]:
    model, specs = _table(name)
    _, window = window_for(range)
    if sort is not None and sort not in {s.name for s in specs}:
        raise HTTPException(400, f"cannot sort by {sort!r}")
    rq = RawQuery(
        window=window,
        network_id=resolve_network(session, network),
        q=q or None,
        filters=_parse_filters(f),
        sort=sort,
        descending=dir != "asc",
    )
    return model, specs, rq


@router.get("/tables", response_model=list[str])
def list_tables() -> list[str]:
    return sorted(_TABLES)


@router.get("/{name}", response_model=RawPage)
def get_raw(
    session: Db,
    name: str,
    range: Annotated[str, Query()] = "6h",
    network: Annotated[str, Query()] = "current",
    q: Annotated[str | None, Query()] = None,
    sort: Annotated[str | None, Query()] = None,
    dir: Annotated[str, Query(pattern="^(asc|desc)$")] = "desc",
    f: Annotated[list[str], Query()] = [],  # noqa: B006 — FastAPI reads the default, never mutates
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RawPage:
    model, specs, rq = _query(session, name, range, network, q, sort, dir, f)
    return queries.raw_page(session, model, specs, rq, limit, offset)


@router.get("/{name}/export.csv")
def export_csv(
    session: Db,
    name: str,
    range: Annotated[str, Query()] = "6h",
    network: Annotated[str, Query()] = "current",
    q: Annotated[str | None, Query()] = None,
    sort: Annotated[str | None, Query()] = None,
    dir: Annotated[str, Query(pattern="^(asc|desc)$")] = "desc",
    f: Annotated[list[str], Query()] = [],  # noqa: B006
) -> StreamingResponse:
    model, specs, rq = _query(session, name, range, network, q, sort, dir, f)
    names = [s.name for s in specs]
    rows = queries.raw_rows(session, model, specs, rq, limit=_EXPORT_CAP)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=names)
    writer.writeheader()
    writer.writerows(rows)
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="netpulse-{name}-{range}.csv"'},
    )

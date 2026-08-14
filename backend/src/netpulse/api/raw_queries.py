"""Raw-data explorer queries — paginated, filterable, sortable access to any sample table, plus
exact SQL-side aggregates. Split out of the main query module (which was a god-module) since this
is a self-contained concern used only by the raw router.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy import ColumnElement, Select, func, or_, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from netpulse.api.schemas import RawAgg, RawColumn, RawPage
from netpulse.quality import percentile

_P95_SAMPLE_CAP = 20_000  # p95 over the most-recent N values; count/min/max/avg are exact


def _scope(
    column: InstrumentedAttribute[int | None], network_id: int | None
) -> list[ColumnElement[bool]]:
    return [column == network_id] if network_id is not None else []


@dataclass(frozen=True, slots=True)
class ColSpec:
    name: str
    type: str  # "number" | "string" | "bool" | "time"
    unit: str | None = None
    enum: bool = False  # offer a distinct-value dropdown filter


@dataclass(frozen=True, slots=True)
class RawQuery:
    window: int
    network_id: int | None
    q: str | None = None
    filters: dict[str, str] | None = None
    sort: str | None = None
    descending: bool = True


def _coerce(val: str, col_type: str) -> object:
    if col_type == "number":
        return float(val)
    if col_type == "bool":
        return val.lower() in ("1", "true", "ok", "yes")
    return val


def _raw_conditions(
    model: type, specs: list[ColSpec], rq: RawQuery
) -> list[ColumnElement[bool]]:
    conds: list[ColumnElement[bool]] = [
        model.ts >= time.time() - rq.window,  # type: ignore[attr-defined]
        *_scope(model.network_id, rq.network_id),  # type: ignore[attr-defined]
    ]
    if rq.q:
        text_cols = [getattr(model, s.name) for s in specs if s.type == "string"]
        if text_cols:
            esc = rq.q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            conds.append(or_(*[c.ilike(f"%{esc}%", escape="\\") for c in text_cols]))
    for col, val in (rq.filters or {}).items():
        spec = next((s for s in specs if s.name == col), None)
        if spec is None:
            continue
        conds.append(getattr(model, col) == _coerce(val, spec.type))
    return conds


def raw_rows(
    session: Session,
    model: type,
    specs: list[ColSpec],
    rq: RawQuery,
    limit: int | None = None,
    offset: int = 0,
) -> list[dict[str, object]]:
    names = [s.name for s in specs]
    sort_col = getattr(model, rq.sort) if rq.sort in names else model.ts  # type: ignore[attr-defined]
    order = sort_col.desc() if rq.descending else sort_col.asc()
    # id is the stable tiebreaker: without it, ties on ts let OFFSET skip/repeat rows.
    stmt: Select[Any] = (
        select(model)
        .where(*_raw_conditions(model, specs, rq))
        .order_by(order, model.id.desc())  # type: ignore[attr-defined]
        .offset(offset)
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    return [{n: getattr(r, n) for n in names} for r in session.scalars(stmt).all()]


def raw_page(
    session: Session,
    model: type,
    specs: list[ColSpec],
    rq: RawQuery,
    limit: int,
    offset: int,
) -> RawPage:
    conds = _raw_conditions(model, specs, rq)
    # Facet values ignore the row filters (only window+network) so a chosen filter can be changed.
    base_conds: list[ColumnElement[bool]] = [
        model.ts >= time.time() - rq.window,  # type: ignore[attr-defined]
        *_scope(model.network_id, rq.network_id),  # type: ignore[attr-defined]
    ]
    total = session.scalar(select(func.count()).select_from(model).where(*conds))
    rows = raw_rows(session, model, specs, rq, limit, offset)
    return RawPage(
        columns=[_column_meta(session, model, s, base_conds) for s in specs],
        rows=rows,
        total=int(total or 0),
        agg=_raw_aggregates(session, model, specs, conds),
    )


def _column_meta(
    session: Session, model: type, spec: ColSpec, conds: list[ColumnElement[bool]]
) -> RawColumn:
    values: list[str] | None = None
    if spec.enum:
        col = getattr(model, spec.name)
        distinct = session.scalars(
            select(col).where(*conds).distinct().order_by(col).limit(50)
        ).all()
        values = [str(v) for v in distinct if v is not None]
    return RawColumn(name=spec.name, type=spec.type, unit=spec.unit, values=values)


def _raw_aggregates(
    session: Session, model: type, specs: list[ColSpec], conds: list[ColumnElement[bool]]
) -> list[RawAgg]:
    numeric = [s for s in specs if s.type == "number"]
    if not numeric:
        return []
    # Exact count/min/max/avg pushed to SQL (O(1) memory), one round-trip for all columns.
    agg_exprs: list[Any] = []
    for spec in numeric:
        col = getattr(model, spec.name)
        agg_exprs += [func.count(col), func.min(col), func.max(col), func.avg(col)]
    summary = session.execute(select(*agg_exprs).where(*conds)).one()

    out: list[RawAgg] = []
    for i, spec in enumerate(numeric):
        count, mn, mx, avg = summary[i * 4 : i * 4 + 4]
        col = getattr(model, spec.name)
        sample = session.scalars(
            select(col)
            .where(*conds, col.is_not(None))
            .order_by(model.ts.desc())  # type: ignore[attr-defined]
            .limit(_P95_SAMPLE_CAP)
        ).all()
        p95 = percentile([float(v) for v in sample], 95) if sample else None
        out.append(RawAgg(
            column=spec.name,
            count=int(count or 0),
            min=float(mn) if mn is not None else None,
            max=float(mx) if mx is not None else None,
            avg=round(float(avg), 2) if avg is not None else None,
            p95=round(p95, 2) if p95 is not None else None,
        ))
    return out

"""Read-side query helpers — turn stored rows into API responses.

The range decides the resolution: 6h reads raw samples, 24h reads 5-min buckets, 7d reads
1-h buckets. Series are split by tag (per target / per resolver) so the frontend draws one
line each. Every read can be scoped to a ``network_id`` (``None`` = all networks) so analysis
follows the PC between home / office / café.
"""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import ColumnElement, Select, func, or_, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from netpulse.aggregation import SOURCES
from netpulse.analysis.attribute import HopStat, attribute
from netpulse.analysis.diurnal import distinct_days, hourly_cells
from netpulse.analysis.stats import block_bootstrap_ci, gilbert_elliott, spearman
from netpulse.analysis.verdict import WindowStats
from netpulse.api.schemas import (
    ActivePoint,
    AnycastOut,
    DiurnalCell,
    DiurnalResponse,
    EventOut,
    FlowOut,
    FlowQualityOut,
    HopPoint,
    HopSeries,
    HopTimeline,
    NetworkOut,
    Point,
    RawAgg,
    RawColumn,
    RawPage,
    Series,
    SeriesResponse,
    Status,
)
from netpulse.config import get_config
from netpulse.db.models import (
    ActiveTest,
    Agg,
    AnycastPop,
    DnsRaw,
    Event,
    Flow,
    FlowQuality,
    Network,
    PingRaw,
    State,
    Traceroute,
    WifiRaw,
)
from netpulse.quality import percentile

_SOURCE_BY_NAME = {s.name: s for s in SOURCES}


def _scope(
    column: InstrumentedAttribute[int | None], network_id: int | None
) -> list[ColumnElement[bool]]:
    return [column == network_id] if network_id is not None else []


def _internet_hosts() -> set[str]:
    return {t.host for t in get_config().targets if t.kind in ("internet", "site", "work")}


def series(
    session: Session,
    metric: str,
    range_key: str,
    resolution: str,
    window: int,
    *,
    network_id: int | None = None,
) -> SeriesResponse:
    start = time.time() - window
    grouped: dict[str, list[Point]] = {}

    if resolution == "raw":
        source = _SOURCE_BY_NAME[metric]
        model = source.model
        rows: Sequence[object] = session.scalars(
            select(model)
            .where(model.ts >= start, *_scope(model.network_id, network_id))  # type: ignore[attr-defined]
            .order_by(model.ts)  # type: ignore[attr-defined]
        ).all()
        for row in rows:
            value = getattr(row, source.value_attr)
            if value is None:
                continue
            tag = getattr(row, source.tag_attr) if source.tag_attr else ""
            grouped.setdefault(tag, []).append(Point(ts=row.ts, avg=value))  # type: ignore[attr-defined]
    else:
        aggs = session.scalars(
            select(Agg)
            .where(
                Agg.metric == metric, Agg.resolution == resolution, Agg.bucket >= start,
                *_scope(Agg.network_id, network_id),
            )
            .order_by(Agg.bucket)
        ).all()
        for agg in aggs:
            grouped.setdefault(agg.tag, []).append(
                Point(ts=agg.bucket, avg=agg.avg, mn=agg.mn, mx=agg.mx, p95=agg.p95)
            )

    return SeriesResponse(
        metric=metric,
        range=range_key,
        resolution=resolution,
        series=[Series(tag=tag, points=pts) for tag, pts in sorted(grouped.items())],
    )


def active_tests(session: Session, window: int, network_id: int | None = None) -> list[ActivePoint]:
    start = time.time() - window
    rows = session.scalars(
        select(ActiveTest)
        .where(ActiveTest.ts >= start, *_scope(ActiveTest.network_id, network_id))
        .order_by(ActiveTest.ts)
    ).all()
    return [
        ActivePoint(
            ts=r.ts, download_mbps=r.download_mbps, upload_mbps=r.upload_mbps,
            idle_latency=r.idle_latency, bufferbloat_ms=r.bufferbloat_ms,
            grade=r.grade, mos=r.mos,
        )
        for r in rows
    ]


def events(
    session: Session, window: int, network_id: int | None = None, limit: int = 200
) -> list[EventOut]:
    start = time.time() - window
    rows = session.scalars(
        select(Event)
        .where(Event.ts >= start, *_scope(Event.network_id, network_id))
        .order_by(Event.ts.desc())
        .limit(limit)
    ).all()
    return [
        EventOut(
            ts=r.ts, end_ts=r.end_ts, kind=r.kind, severity=r.severity, detail=r.detail,
            duration=(r.end_ts - r.ts) if r.end_ts else None,
        )
        for r in rows
    ]


def top_flows(
    session: Session, window: int, network_id: int | None = None, limit: int = 30
) -> list[FlowOut]:
    start = time.time() - window
    rows = session.execute(
        select(
            Flow.remote_ip,
            func.max(Flow.rdns), func.max(Flow.asn), func.max(Flow.app),
            func.sum(Flow.conns),
        )
        .where(Flow.ts >= start, *_scope(Flow.network_id, network_id))
        .group_by(Flow.remote_ip)
        .order_by(func.sum(Flow.conns).desc())
        .limit(limit)
    ).all()
    return [
        FlowOut(remote_ip=ip, rdns=rdns, asn=asn, app=app, conns=int(conns))
        for ip, rdns, asn, app, conns in rows
    ]


def networks(session: Session) -> list[NetworkOut]:
    current = current_network_id(session)
    rows = session.scalars(select(Network).order_by(Network.last_seen.desc())).all()
    return [
        NetworkOut(
            id=n.id, label=n.label, ssid=n.ssid, gateway_ip=n.gateway_ip,
            gateway_mac=n.gateway_mac, interface=n.interface,
            first_seen=n.first_seen, last_seen=n.last_seen, is_current=n.id == current,
        )
        for n in rows
    ]


def latest_anycast(session: Session, network_id: int | None) -> list[AnycastOut]:
    rows = session.scalars(
        select(AnycastPop)
        .where(*_scope(AnycastPop.network_id, network_id))
        .order_by(AnycastPop.ts.desc())
    ).all()
    seen: set[str] = set()
    out: list[AnycastOut] = []
    for r in rows:
        key = f"{r.provider}:{r.target}"
        if key in seen:
            continue
        seen.add(key)
        out.append(AnycastOut(
            provider=r.provider, target=r.target, colo=r.colo, colo_country=r.colo_country,
            client_country=r.client_country, out_of_country=r.out_of_country, ts=r.ts,
        ))
    return out


def recent_flow_quality(
    session: Session, window: int, network_id: int | None, limit: int = 40
) -> list[FlowQualityOut]:
    """Latest passive transport-quality per endpoint over the window, worst congestion first."""
    start = time.time() - window
    rows = session.scalars(
        select(FlowQuality)
        .where(FlowQuality.ts >= start, *_scope(FlowQuality.network_id, network_id))
        .order_by(FlowQuality.ts.desc())
    ).all()
    latest: dict[str, FlowQuality] = {}
    for r in rows:
        latest.setdefault(r.remote_ip, r)  # first seen = most recent (desc order)

    def excess(r: FlowQuality) -> float | None:
        if r.srtt_ms is not None and r.min_rtt_ms is not None:
            return round(max(0.0, r.srtt_ms - r.min_rtt_ms), 1)
        return None

    out = [
        FlowQualityOut(
            remote_ip=r.remote_ip, asn=r.asn, app=r.app, srtt_ms=r.srtt_ms,
            min_rtt_ms=r.min_rtt_ms, excess_ms=excess(r), retrans_total=r.retrans_total,
            delivery_mbps=r.delivery_mbps, sockets=r.sockets,
        )
        for r in latest.values()
    ]
    out.sort(key=lambda f: f.excess_ms or 0, reverse=True)
    return out[:limit]


def diurnal(
    session: Session, metric: str, window: int, network_id: int | None
) -> DiurnalResponse:
    """Per-hour-of-day distribution of loss or latency over internet targets, with CIs and an
    honest days-observed flag (a diurnal claim needs the pattern to repeat across days)."""
    start = time.time() - window
    pings = session.scalars(
        select(PingRaw).where(
            PingRaw.ts >= start, PingRaw.target.in_(_internet_hosts()),
            *_scope(PingRaw.network_id, network_id),
        )
    ).all()
    if metric == "latency":
        samples = [(p.ts, p.rtt_avg) for p in pings if p.rtt_avg is not None]
    else:
        samples = [(p.ts, p.loss_pct) for p in pings]
    days = distinct_days(samples)
    cells = [DiurnalCell(**asdict(c)) for c in hourly_cells(samples)]
    return DiurnalResponse(metric=metric, days_observed=days, sufficient=days >= 3, cells=cells)


def current_network_id(session: Session) -> int | None:
    """The most recently seen network (the collector updates ``last_seen`` every cycle)."""
    return session.scalar(select(Network.id).order_by(Network.last_seen.desc()).limit(1))


def status(session: Session, window: int, interface: str, network_id: int | None = None) -> Status:
    now = time.time()
    start = now - window
    recent = session.scalars(
        select(PingRaw).where(PingRaw.ts >= now - 60, *_scope(PingRaw.network_id, network_id))
    ).all()
    reachable = [r for r in recent if r.loss_pct < 100 and r.rtt_avg is not None]
    latest_ping = min(reachable, key=lambda r: r.rtt_avg) if reachable else None  # type: ignore[arg-type,return-value]
    current_loss = min((r.loss_pct for r in recent), default=None)

    latest_wifi = session.scalars(
        select(WifiRaw)
        .where(*_scope(WifiRaw.network_id, network_id))
        .order_by(WifiRaw.ts.desc())
        .limit(1)
    ).first()
    latest_active = session.scalars(
        select(ActiveTest)
        .where(*_scope(ActiveTest.network_id, network_id))
        .order_by(ActiveTest.ts.desc())
        .limit(1)
    ).first()
    outages = session.scalar(
        select(func.count())
        .select_from(Event)
        .where(Event.kind == "outage", Event.ts >= start, *_scope(Event.network_id, network_id))
    )
    ipv4 = session.get(State, "public_ipv4")
    ipv6 = session.get(State, "public_ipv6")

    return Status(
        online=bool(reachable),
        current_rtt=latest_ping.rtt_avg if latest_ping else None,
        current_loss=current_loss,
        wifi_signal_dbm=latest_wifi.signal_dbm if latest_wifi else None,
        wifi_bitrate=latest_wifi.tx_bitrate if latest_wifi else None,
        wifi_ssid=latest_wifi.ssid if latest_wifi else None,
        public_ipv4=ipv4.value if ipv4 else None,
        public_ipv6=ipv6.value if ipv6 else None,
        outages_in_range=int(outages or 0),
        latest_download_mbps=latest_active.download_mbps if latest_active else None,
        latest_upload_mbps=latest_active.upload_mbps if latest_active else None,
        latest_grade=latest_active.grade if latest_active else None,
        latest_mos=latest_active.mos if latest_active else None,
        interface=interface,
    )


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


def _coerce(val: str, col_type: str) -> object:
    if col_type == "number":
        return float(val)
    if col_type == "bool":
        return val.lower() in ("1", "true", "ok", "yes")
    return val


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


_P95_SAMPLE_CAP = 20_000  # p95 over the most-recent N values; count/min/max/avg are exact


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


def hop_timeline(
    session: Session, target: str, window: int, network_id: int | None
) -> HopTimeline:
    start = time.time() - window
    rows = session.scalars(
        select(Traceroute)
        .where(
            Traceroute.target == target, Traceroute.ts >= start,
            *_scope(Traceroute.network_id, network_id),
        )
        .order_by(Traceroute.ts)
    ).all()
    by_hop: dict[int, list[Traceroute]] = {}
    host_by_hop: dict[int, str] = {}
    for r in rows:
        by_hop.setdefault(r.hop, []).append(r)
        if r.host:
            host_by_hop[r.hop] = r.host
    hops = []
    for hop, hop_rows in sorted(by_hop.items()):
        losses = [r.loss_pct for r in hop_rows if r.loss_pct is not None]
        hops.append(HopSeries(
            hop=hop,
            host=host_by_hop.get(hop),
            avg_loss=sum(losses) / len(losses) if losses else 0.0,
            points=[HopPoint(ts=r.ts, loss_pct=r.loss_pct, rtt_ms=r.rtt_ms) for r in hop_rows],
        ))
    return HopTimeline(target=target, hops=hops)


_CORR_BUCKET = 300  # 5-min buckets for aligning loss vs WiFi retry-rate


def hop_stats(
    session: Session, target: str, start: float, network_id: int | None
) -> list[HopStat]:
    """Average per-hop loss toward a target over the window (from mtr history)."""
    rows = session.scalars(
        select(Traceroute).where(
            Traceroute.target == target, Traceroute.ts >= start,
            *_scope(Traceroute.network_id, network_id),
        )
    ).all()
    loss_by_hop: dict[int, list[float]] = {}
    host_by_hop: dict[int, str] = {}
    for r in rows:
        if r.loss_pct is not None:
            loss_by_hop.setdefault(r.hop, []).append(r.loss_pct)
        if r.host:
            host_by_hop[r.hop] = r.host
    return [
        HopStat(hop=h, host=host_by_hop.get(h), loss_pct=sum(v) / len(v))
        for h, v in sorted(loss_by_hop.items())
    ]


_MIN_CORR_BUCKETS = 6  # too few buckets → correlation isn't trustworthy, report None


def _loss_retry_corr(
    session: Session, hosts: set[str], start: float, network_id: int | None
) -> float | None:
    """Rank-correlate per-bucket internet loss with the WiFi **retry ratio**
    (Δretries / Δtx-packets within the bucket). A raw retry-count delta would just track how
    much traffic was sent; the ratio is a real rate. Buckets spanning a counter reset/roam
    (Δ<0 or no traffic) are dropped, and Spearman (not Pearson) suits the heavy-tailed data.
    Returns None below a minimum bucket count so a chance correlation can't flip attribution."""
    pings = session.scalars(
        select(PingRaw).where(
            PingRaw.ts >= start, PingRaw.target.in_(hosts), *_scope(PingRaw.network_id, network_id)
        )
    ).all()
    wifis = session.scalars(
        select(WifiRaw).where(WifiRaw.ts >= start, *_scope(WifiRaw.network_id, network_id))
    ).all()
    loss_by_b: dict[int, list[float]] = {}
    for p in pings:
        loss_by_b.setdefault(int(p.ts) // _CORR_BUCKET, []).append(p.loss_pct)
    retries_by_b: dict[int, list[int]] = {}
    packets_by_b: dict[int, list[int]] = {}
    for w in wifis:
        if w.tx_retries is not None and w.tx_packets is not None:
            b = int(w.ts) // _CORR_BUCKET
            retries_by_b.setdefault(b, []).append(w.tx_retries)
            packets_by_b.setdefault(b, []).append(w.tx_packets)

    xs: list[float] = []
    ys: list[float] = []
    for b in sorted(set(loss_by_b) & set(retries_by_b)):
        d_retries = max(retries_by_b[b]) - min(retries_by_b[b])
        d_packets = max(packets_by_b[b]) - min(packets_by_b[b])
        if d_retries < 0 or d_packets <= 0:  # counter reset / roam / no traffic
            continue
        xs.append(sum(loss_by_b[b]) / len(loss_by_b[b]))
        ys.append(d_retries / d_packets)
    if len(xs) < _MIN_CORR_BUCKETS:
        return None
    return spearman(xs, ys)


def gather_stats(
    session: Session, window: int, window_label: str, network_id: int | None = None
) -> WindowStats:
    """Roll the stored samples in a window into the inputs the verdict engine reasons over."""
    now = time.time()
    start = now - window
    hosts = _internet_hosts()

    pings = session.scalars(
        select(PingRaw).where(
            PingRaw.ts >= start, PingRaw.target.in_(hosts), *_scope(PingRaw.network_id, network_id)
        )
    ).all()
    rtts = [p.rtt_avg for p in pings if p.rtt_avg is not None]
    jitters = [p.jitter for p in pings if p.jitter is not None]

    per_target: dict[str, list[float]] = {}
    for p in pings:
        per_target.setdefault(p.target, []).append(p.loss_pct)
    worst_target = None
    worst_loss_p95 = None
    loss_ci = None
    loss_burst = None
    if per_target:
        host, vals = max(per_target.items(), key=lambda kv: sum(kv[1]) / len(kv[1]))
        worst_target = (host, sum(vals) / len(vals))
        # Score input = the worst path's p95 loss, so bursty drops (the real symptom) surface
        # instead of being averaged away across a mostly-healthy window.
        worst_loss_p95 = max(percentile(v, 95) for v in per_target.values())
        loss_ci = block_bootstrap_ci(vals) if len(vals) > 10 else None
        _, loss_burst = gilbert_elliott([v > 0 for v in vals])

    # Empirical latency floor: the fastest RTT ever seen on this path is its physical minimum;
    # excess above it is congestion/queuing, not distance (the audit's min-RTT baseline).
    rtt_mins = [p.rtt_min for p in pings if p.rtt_min is not None]
    floor = min(rtt_mins) if rtt_mins else None
    latency_p95 = percentile(rtts, 95) if rtts else None
    latency_excess = (
        max(0.0, latency_p95 - floor) if latency_p95 is not None and floor is not None else None
    )

    outages = session.scalars(
        select(Event).where(
            Event.kind == "outage", Event.ts >= start, *_scope(Event.network_id, network_id)
        )
    ).all()
    downtime = sum((o.end_ts or now) - max(o.ts, start) for o in outages)
    worst_outage = max(((o.end_ts or now) - o.ts for o in outages), default=None)
    worst_cause = max(outages, key=lambda o: (o.end_ts or now) - o.ts).detail if outages else None

    wifi = session.scalars(
        select(WifiRaw).where(WifiRaw.ts >= start, *_scope(WifiRaw.network_id, network_id))
    ).all()
    signals = [w.signal_dbm for w in wifi if w.signal_dbm is not None]
    retries = [w.tx_retries for w in wifi if w.tx_retries is not None]

    dns = session.scalars(
        select(DnsRaw).where(DnsRaw.ts >= start, *_scope(DnsRaw.network_id, network_id))
    ).all()
    dns_fail = sum(1 for d in dns if not d.ok)

    latest_active = session.scalars(
        select(ActiveTest)
        .where(ActiveTest.ts >= start, *_scope(ActiveTest.network_id, network_id))
        .order_by(ActiveTest.ts.desc())
        .limit(1)
    ).first()

    anycast_out = _anycast_out_of_country(session, start, network_id)
    signal_avg = sum(signals) / len(signals) if signals else None
    corr = _loss_retry_corr(session, hosts, start, network_id)
    primary = next((t.host for t in get_config().targets if t.kind == "internet"), None)
    hops = hop_stats(session, primary, start, network_id) if primary else []
    attribution = attribute(hops, corr, wifi_weak=signal_avg is not None and signal_avg <= -72)

    return WindowStats(
        loss=worst_loss_p95,
        loss_ci=loss_ci,
        loss_burst_len=loss_burst,
        latency=latency_p95,
        latency_excess=latency_excess,
        jitter=percentile(jitters, 95) if jitters else None,
        bufferbloat=latest_active.bufferbloat_ms if latest_active else None,
        availability=max(0.0, 100 * (1 - downtime / window)) if window else None,
        outage_count=len(outages),
        downtime_s=downtime,
        worst_outage_s=worst_outage,
        worst_outage_cause=worst_cause,
        worst_target=worst_target,
        wifi_signal_avg=signal_avg,
        wifi_retries_max=max(retries) if retries else None,
        dns_fail=dns_fail,
        dns_total=len(dns),
        attribution=attribution,
        loss_retry_corr=corr,
        anycast_out=anycast_out,
        window_label=window_label,
    )


def _anycast_out_of_country(
    session: Session, start: float, network_id: int | None
) -> list[tuple[str, str, str]]:
    """Latest out-of-country POP per provider (deduped) over the window."""
    rows = session.scalars(
        select(AnycastPop)
        .where(AnycastPop.ts >= start, *_scope(AnycastPop.network_id, network_id))
        .order_by(AnycastPop.ts.desc())
    ).all()
    seen: set[str] = set()
    out: list[tuple[str, str, str]] = []
    for r in rows:
        if r.provider in seen:
            continue
        seen.add(r.provider)
        if r.out_of_country and r.colo and r.colo_country:
            out.append((r.provider, r.colo, r.colo_country))
    return out

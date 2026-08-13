"""Read-side query helpers — turn stored rows into API responses.

The range decides the resolution: 6h reads raw samples, 24h reads 5-min buckets, 7d reads
1-h buckets. Series are split by tag (per target / per resolver) so the frontend draws one
line each. Every read can be scoped to a ``network_id`` (``None`` = all networks) so analysis
follows the PC between home / office / café.
"""

from __future__ import annotations

import time
from collections.abc import Sequence

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from netpulse.aggregation import SOURCES
from netpulse.analysis.verdict import WindowStats
from netpulse.api.schemas import (
    ActivePoint,
    EventOut,
    FlowOut,
    NetworkOut,
    Point,
    Series,
    SeriesResponse,
    Status,
)
from netpulse.config import get_config
from netpulse.db.models import (
    ActiveTest,
    Agg,
    DnsRaw,
    Event,
    Flow,
    Network,
    PingRaw,
    State,
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
    losses = [p.loss_pct for p in pings]
    rtts = [p.rtt_avg for p in pings if p.rtt_avg is not None]
    jitters = [p.jitter for p in pings if p.jitter is not None]

    per_target: dict[str, list[float]] = {}
    for p in pings:
        per_target.setdefault(p.target, []).append(p.loss_pct)
    worst_target = None
    if per_target:
        host, vals = max(per_target.items(), key=lambda kv: sum(kv[1]) / len(kv[1]))
        worst_target = (host, sum(vals) / len(vals))

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

    return WindowStats(
        loss=sum(losses) / len(losses) if losses else None,
        latency=percentile(rtts, 95) if rtts else None,
        jitter=sum(jitters) / len(jitters) if jitters else None,
        bufferbloat=latest_active.bufferbloat_ms if latest_active else None,
        availability=max(0.0, 100 * (1 - downtime / window)) if window else None,
        outage_count=len(outages),
        downtime_s=downtime,
        worst_outage_s=worst_outage,
        worst_outage_cause=worst_cause,
        worst_target=worst_target,
        wifi_signal_avg=sum(signals) / len(signals) if signals else None,
        wifi_retries_max=max(retries) if retries else None,
        dns_fail=dns_fail,
        dns_total=len(dns),
        window_label=window_label,
    )

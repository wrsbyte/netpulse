"""Read-side query helpers — turn stored rows into API responses.

The range decides the resolution: 6h reads raw samples, 24h reads 5-min buckets, 7d reads
1-h buckets. Series are split by tag (per target / per resolver) so the frontend draws one
line each.
"""

from __future__ import annotations

import time

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from netpulse.aggregation import SOURCES
from netpulse.api.schemas import (
    ActivePoint,
    EventOut,
    FlowOut,
    Point,
    Series,
    SeriesResponse,
    Status,
)
from netpulse.db.models import ActiveTest, Agg, Event, Flow, PingRaw, State, WifiRaw

_SOURCE_BY_NAME = {s.name: s for s in SOURCES}


def series(
    session: Session, metric: str, range_key: str, resolution: str, window: int
) -> SeriesResponse:
    start = time.time() - window
    grouped: dict[str, list[Point]] = {}

    if resolution == "raw":
        source = _SOURCE_BY_NAME[metric]
        model = source.model
        rows = session.scalars(
            select(model).where(model.ts >= start).order_by(model.ts)  # type: ignore[attr-defined]
        ).all()
        for row in rows:
            value = getattr(row, source.value_attr)
            if value is None:
                continue
            tag = getattr(row, source.tag_attr) if source.tag_attr else ""
            grouped.setdefault(tag, []).append(Point(ts=row.ts, avg=value))  # type: ignore[attr-defined]
    else:
        rows = session.scalars(
            select(Agg)
            .where(Agg.metric == metric, Agg.resolution == resolution, Agg.bucket >= start)
            .order_by(Agg.bucket)
        ).all()
        for agg in rows:
            grouped.setdefault(agg.tag, []).append(
                Point(ts=agg.bucket, avg=agg.avg, mn=agg.mn, mx=agg.mx, p95=agg.p95)
            )

    return SeriesResponse(
        metric=metric,
        range=range_key,
        resolution=resolution,
        series=[Series(tag=tag, points=pts) for tag, pts in sorted(grouped.items())],
    )


def active_tests(session: Session, window: int) -> list[ActivePoint]:
    start = time.time() - window
    rows = session.scalars(
        select(ActiveTest).where(ActiveTest.ts >= start).order_by(ActiveTest.ts)
    ).all()
    return [
        ActivePoint(
            ts=r.ts, download_mbps=r.download_mbps, upload_mbps=r.upload_mbps,
            idle_latency=r.idle_latency, bufferbloat_ms=r.bufferbloat_ms,
            grade=r.grade, mos=r.mos,
        )
        for r in rows
    ]


def events(session: Session, window: int, limit: int = 200) -> list[EventOut]:
    start = time.time() - window
    rows = session.scalars(
        select(Event).where(Event.ts >= start).order_by(Event.ts.desc()).limit(limit)
    ).all()
    return [
        EventOut(
            ts=r.ts, end_ts=r.end_ts, kind=r.kind, severity=r.severity, detail=r.detail,
            duration=(r.end_ts - r.ts) if r.end_ts else None,
        )
        for r in rows
    ]


def top_flows(session: Session, window: int, limit: int = 30) -> list[FlowOut]:
    start = time.time() - window
    rows = session.execute(
        select(
            Flow.remote_ip,
            func.max(Flow.rdns), func.max(Flow.asn), func.max(Flow.app),
            func.sum(Flow.conns),
        )
        .where(Flow.ts >= start)
        .group_by(Flow.remote_ip)
        .order_by(func.sum(Flow.conns).desc())
        .limit(limit)
    ).all()
    return [
        FlowOut(remote_ip=ip, rdns=rdns, asn=asn, app=app, conns=int(conns))
        for ip, rdns, asn, app, conns in rows
    ]


def status(session: Session, window: int, interface: str) -> Status:
    now = time.time()
    start = now - window
    # "Current" KPIs come from the freshest raw samples (last minute), not the rollup —
    # the rollup lags by its cadence and would leave the dashboard blank right after boot.
    recent = session.scalars(select(PingRaw).where(PingRaw.ts >= now - 60)).all()
    reachable = [r for r in recent if r.loss_pct < 100 and r.rtt_avg is not None]
    latest_ping = min(reachable, key=lambda r: r.rtt_avg) if reachable else None  # type: ignore[arg-type,return-value]
    current_loss = min((r.loss_pct for r in recent), default=None)

    latest_wifi = session.scalars(select(WifiRaw).order_by(WifiRaw.ts.desc()).limit(1)).first()
    latest_active = session.scalars(
        select(ActiveTest).order_by(ActiveTest.ts.desc()).limit(1)
    ).first()
    outages = session.scalar(
        select(func.count()).select_from(Event).where(Event.kind == "outage", Event.ts >= start)
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

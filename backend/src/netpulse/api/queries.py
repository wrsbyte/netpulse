"""Read-side query helpers — turn stored rows into API responses.

The range decides the resolution: 6h reads raw samples, 24h reads 5-min buckets, 7d reads
1-h buckets. Series are split by tag (per target / per resolver) so the frontend draws one
line each. Every read can be scoped to a ``network_id`` (``None`` = all networks) so analysis
follows the PC between home / office / café.
"""

from __future__ import annotations

import json
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import ColumnElement, Select, func, or_, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from netpulse.aggregation import SOURCES
from netpulse.analysis.attribute import HopStat, attribute
from netpulse.analysis.diurnal import distinct_days, hourly_cells
from netpulse.analysis.experience import ExperienceInputs, assess
from netpulse.analysis.geo import locate_colo, locate_country
from netpulse.analysis.segment import classify as segment_classify
from netpulse.analysis.sla import Measured as SlaMeasured
from netpulse.analysis.sla import SlaTargets
from netpulse.analysis.sla import assess as assess_sla
from netpulse.analysis.stats import (
    block_bootstrap_ci,
    blocked_seconds,
    covered_seconds,
    gilbert_elliott,
    spearman,
)
from netpulse.analysis.verdict import WindowStats
from netpulse.analysis.wifi_channel import ChannelAdvice
from netpulse.analysis.wifi_channel import analyze as analyze_channel
from netpulse.analysis.wifi_channel import continuous_hours as channel_continuous_hours
from netpulse.api.schemas import (
    ActivePoint,
    ActivityOut,
    AnycastOut,
    DiurnalCell,
    DiurnalResponse,
    DnsCompareRow,
    EventOut,
    ExperienceOut,
    FlowOut,
    FlowQualityOut,
    GeoArc,
    GeoHop,
    GeoPoint,
    GeoResponse,
    HopPoint,
    HopSeries,
    HopTimeline,
    MetricOut,
    NetworkOut,
    Point,
    RawAgg,
    RawColumn,
    RawPage,
    Series,
    SeriesResponse,
    ServiceQualityOut,
    SlaLineOut,
    SlaReportOut,
    Status,
)
from netpulse.config import Target, get_config
from netpulse.db.models import (
    ActiveTest,
    Agg,
    AnycastPop,
    DnsRaw,
    Event,
    Flow,
    FlowQuality,
    HopLocation,
    Network,
    PingRaw,
    RegionalBaseline,
    State,
    ThroughputRaw,
    Traceroute,
    WifiRaw,
    WifiScan,
)
from netpulse.external.ripe_atlas import percentile_rank
from netpulse.quality import percentile

_SOURCE_BY_NAME = {s.name: s for s in SOURCES}
_COVERAGE_MAX_GAP = 60.0  # s between pings above which the collector was down (suspend), not idle
_SCAN_GUARD = 4.0  # s around a WiFi scan whose ping samples are radio-off-channel artifacts
_SPEEDTEST_BEFORE = 5  # s before a speedtest ts to start excluding (the saturation window)
_SPEEDTEST_AFTER = 55  # s after a speedtest ts to keep excluding


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


def geo_map(session: Session, network_id: int | None) -> GeoResponse:
    """You + the CDN POPs serving you, geolocated and annotated with the RTT/loss actually measured
    to each — so the map shows not just where traffic goes but how good each path is."""
    pops = latest_anycast(session, network_id)
    measured = _measured_by_target(session, network_id)
    client_cc = next((p.client_country for p in pops if p.client_country), None)
    you = locate_country(client_cc)
    points: list[GeoPoint] = []
    arcs: list[GeoArc] = []
    if you:
        gw = _gateway_host()
        gw_rtt, gw_loss = measured.get(gw, (None, None)) if gw else (None, None)
        points.append(GeoPoint(
            lat=you[0], lon=you[1], label=f"You ({client_cc})", kind="you", out_of_country=False,
            rtt_ms=gw_rtt, loss_pct=gw_loss,
        ))
    for p in pops:
        loc = locate_colo(p.colo)
        if loc is None:
            continue
        rtt, loss = measured.get(p.target, (None, None))
        label = f"{p.provider.title()} {p.colo} ({p.colo_country})"
        points.append(GeoPoint(
            lat=loc[0], lon=loc[1], label=label, kind="pop", out_of_country=p.out_of_country,
            provider=p.provider, target=p.target, rtt_ms=rtt, loss_pct=loss,
        ))
        if you:
            arcs.append(GeoArc(
                from_lat=you[0], from_lon=you[1], to_lat=loc[0], to_lon=loc[1],
                out_of_country=p.out_of_country, rtt_ms=rtt, loss_pct=loss,
            ))
    placed = {(round(p.lat, 1), round(p.lon, 1)) for p in points}
    svc_points, svc_arcs = _service_points(session, network_id, client_cc, you, placed)
    points.extend(svc_points)
    arcs.extend(svc_arcs)
    target, path = _hop_path(session, network_id)
    return GeoResponse(points=points, arcs=arcs, path=path, path_target=target)


def _service_name(app: str | None, asn: str | None) -> str:
    """Human label for a flow: its classified app, else a named ASN org, else the bare ASN."""
    num = (asn or "").removeprefix("AS")
    return app or _ASN_ORG.get(num, "") or (f"AS{num}" if num else "Unknown")


def _located_hops(session: Session) -> dict[str, HopLocation]:
    return {
        loc.ip: loc
        for loc in session.scalars(select(HopLocation).where(HopLocation.located)).all()
    }


def _plottable(lat: float | None, lon: float | None) -> bool:
    """Reject (0,0) null-island coordinates — RIPEstat returns them for un-geolocatable IPs, and
    plotting them draws arcs/lines into the ocean off West Africa."""
    return lat is not None and lon is not None and not (abs(lat) < 0.5 and abs(lon) < 0.5)


def _service_points(
    session: Session,
    network_id: int | None,
    client_cc: str | None,
    you: tuple[float, float] | None,
    placed: set[tuple[float, float]],
) -> tuple[list[GeoPoint], list[GeoArc]]:
    """Every service you actually talk to, geolocated (RIPEstat, cached) and sized by its base RTT
    — so the map shows all your CDNs/destinations, not just the one anycast POP we can trace."""
    start = time.time() - 1800
    rows = session.scalars(
        select(FlowQuality)
        .where(FlowQuality.ts >= start, *_scope(FlowQuality.network_id, network_id))
        .order_by(FlowQuality.ts.desc())
    ).all()
    latest: dict[str, FlowQuality] = {}
    for r in rows:
        latest.setdefault(r.remote_ip, r)
    locations = _located_hops(session)
    best: dict[str, tuple[str, float, float, str | None, str | None, float]] = {}
    goodput: dict[str, float] = {}
    for r in latest.values():
        loc = locations.get(r.remote_ip)
        if loc is None or loc.lat is None or loc.lon is None:
            continue
        service = _service_name(r.app, r.asn)
        goodput[service] = goodput.get(service, 0.0) + (r.delivery_mbps or 0.0)
        rtt = r.min_rtt_ms if r.min_rtt_ms is not None else (r.srtt_ms or 1e9)
        if service not in best or rtt < best[service][5]:
            best[service] = (r.remote_ip, loc.lat, loc.lon, loc.city, loc.country, rtt)

    points: list[GeoPoint] = []
    arcs: list[GeoArc] = []
    used = set(placed)
    for service in sorted(goodput, key=lambda s: goodput[s], reverse=True)[:8]:
        ip, lat, lon, city, country, rtt = best[service]
        if not _plottable(lat, lon):  # skip null-island (0,0) geoloc failures
            continue
        coord = (round(lat, 1), round(lon, 1))
        if coord in used:  # a shared coord is a country/registry centroid — don't stack labels
            continue
        used.add(coord)
        abroad = client_cc is not None and country is not None and country != client_cc
        rtt_val = rtt if rtt < 1e9 else None
        where = city or (f"{country}, approx" if country else "approx")
        points.append(GeoPoint(
            lat=lat, lon=lon, label=f"{service} ({where})",
            kind="service", out_of_country=abroad, provider=service, target=ip,
            rtt_ms=rtt_val, loss_pct=None,
        ))
        if you:
            arcs.append(GeoArc(
                from_lat=you[0], from_lon=you[1], to_lat=lat, to_lon=lon,
                out_of_country=abroad, rtt_ms=rtt_val, loss_pct=None,
            ))
    return points, arcs


def _hop_path(session: Session, network_id: int | None) -> tuple[str | None, list[GeoHop]]:
    """The geolocated hop-by-hop route to the primary internet target: each public hop RIPEstat
    could place, in order, with the RTT/loss measured at that hop."""
    target = next((t.host for t in get_config().targets if t.kind == "internet"), None)
    if target is None:
        return (None, [])
    latest_ts = session.scalar(
        select(func.max(Traceroute.ts)).where(
            Traceroute.target == target, *_scope(Traceroute.network_id, network_id)
        )
    )
    if latest_ts is None:
        return (target, [])
    hops = session.scalars(
        select(Traceroute)
        .where(
            Traceroute.target == target, Traceroute.ts == latest_ts,
            *_scope(Traceroute.network_id, network_id),
        )
        .order_by(Traceroute.hop)
    ).all()
    locations = _located_hops(session)
    path: list[GeoHop] = []
    for h in hops:
        loc = locations.get(h.host) if h.host else None
        if loc is None or loc.lat is None or loc.lon is None or not _plottable(loc.lat, loc.lon):
            continue
        path.append(GeoHop(
            hop=h.hop, ip=h.host or "", lat=loc.lat, lon=loc.lon, city=loc.city,
            country=loc.country, rtt_ms=h.rtt_ms, loss_pct=h.loss_pct,
        ))
    return (target, path)


def _gateway_host() -> str | None:
    return next((t.host for t in get_config().targets if t.kind == "lan"), None)


def _measured_by_target(
    session: Session, network_id: int | None
) -> dict[str, tuple[float | None, float | None]]:
    """Avg RTT and loss per probed target over the last 30 min — the live quality of each path."""
    start = time.time() - 1800
    rows = session.scalars(
        select(PingRaw).where(PingRaw.ts >= start, *_scope(PingRaw.network_id, network_id))
    ).all()
    by_target: dict[str, list[PingRaw]] = {}
    for p in rows:
        by_target.setdefault(p.target, []).append(p)
    out: dict[str, tuple[float | None, float | None]] = {}
    for target, ps in by_target.items():
        rtts = [p.rtt_avg for p in ps if p.rtt_avg is not None]
        out[target] = (
            sum(rtts) / len(rtts) if rtts else None,
            sum(p.loss_pct for p in ps) / len(ps),
        )
    return out


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


# Keyed by the numeric ASN as stored (no "AS" prefix), to name the common orgs the flow classifier
# doesn't label — otherwise they show as a bare number.
_ASN_ORG = {
    "8075": "Microsoft",
    "13335": "Cloudflare",
    "16509": "Amazon AWS",
    "14618": "Amazon AWS",
    "15169": "Google",
    "396982": "Google Cloud",
    "396356": "Google",
    "32934": "Meta",
    "20940": "Akamai",
    "36459": "GitHub",
    "13999": "Mega Cable (ISP)",
    "54113": "Fastly",
    "399358": "Datacamp/CDN77",
    "20454": "SHF",
}


def sla(session: Session, window: int, window_label: str, network_id: int | None) -> SlaReportOut:
    """Measured delivery vs the ISP contract: median down/up capacity and idle latency from the
    speedtests, and uptime from recorded outages, over the window."""
    cfg = get_config().sla
    now = time.time()
    start = now - window
    actives = session.scalars(
        select(ActiveTest).where(ActiveTest.ts >= start, *_scope(ActiveTest.network_id, network_id))
    ).all()
    downs = [a.download_mbps for a in actives if a.download_mbps is not None]
    ups = [a.upload_mbps for a in actives if a.upload_mbps is not None]
    idles = [a.idle_latency for a in actives if a.idle_latency is not None]
    outages = session.scalars(
        select(Event).where(
            Event.kind == "outage", Event.ts >= start, *_scope(Event.network_id, network_id)
        )
    ).all()
    downtime = sum((o.end_ts or now) - max(o.ts, start) for o in outages)
    uptime = max(0.0, 100 * (1 - downtime / window)) if window else None
    measured = SlaMeasured(
        download_mbps=percentile(downs, 50) if downs else None,
        upload_mbps=percentile(ups, 50) if ups else None,
        uptime_pct=uptime,
        latency_ms=percentile(idles, 50) if idles else None,
    )
    report = assess_sla(
        SlaTargets(cfg.download_mbps, cfg.upload_mbps, cfg.uptime_pct, cfg.latency_ms), measured
    )
    return SlaReportOut(
        configured=report.configured, window_label=window_label, breaches=report.breaches,
        lines=[
            SlaLineOut(
                metric=line.metric, contracted=line.contracted, measured=line.measured,
                delivered_pct=line.delivered_pct, meets=line.meets,
            )
            for line in report.lines
        ],
    )


def flow_services(
    session: Session, window: int, network_id: int | None, limit: int = 12
) -> list[ServiceQualityOut]:
    """Passive transport quality collapsed by SERVICE (app name, else ASN org) instead of a wall of
    raw endpoint IPs — how each service you actually use is performing, most-used first."""
    start = time.time() - window
    rows = session.scalars(
        select(FlowQuality)
        .where(FlowQuality.ts >= start, *_scope(FlowQuality.network_id, network_id))
        .order_by(FlowQuality.ts.desc())
    ).all()
    latest: dict[str, FlowQuality] = {}
    for r in rows:
        latest.setdefault(r.remote_ip, r)  # most-recent sample per endpoint

    groups: dict[str, list[FlowQuality]] = {}
    for r in latest.values():
        groups.setdefault(_service_name(r.app, r.asn), []).append(r)

    out: list[ServiceQualityOut] = []
    for service, flows in groups.items():
        base = [f.min_rtt_ms for f in flows if f.min_rtt_ms is not None]
        excesses = [
            max(0.0, f.srtt_ms - f.min_rtt_ms)
            for f in flows
            if f.srtt_ms is not None and f.min_rtt_ms is not None
        ]
        goodputs = [f.delivery_mbps for f in flows if f.delivery_mbps is not None]
        out.append(ServiceQualityOut(
            service=service,
            asn=next((f.asn for f in flows if f.asn), None),
            endpoints=len(flows),
            rtt_ms=round(percentile(base, 50), 1) if base else None,
            worst_excess_ms=round(max(excesses), 1) if excesses else None,
            retrans_total=sum(f.retrans_total or 0 for f in flows),
            delivery_mbps=round(sum(goodputs), 2) if goodputs else None,
        ))
    out.sort(key=lambda s: s.delivery_mbps or 0, reverse=True)
    return out[:limit]


def dns_compare(
    session: Session, window: int, network_id: int | None
) -> list[DnsCompareRow]:
    """Reliable side-by-side of the resolvers over the window: median, p95, jitter (IQR) and
    failure rate — the honest basis for 'which DNS' instead of a single ping."""
    start = time.time() - window
    rows = session.scalars(
        select(DnsRaw).where(DnsRaw.ts >= start, *_scope(DnsRaw.network_id, network_id))
    ).all()
    by_resolver: dict[str, list[DnsRaw]] = {}
    for r in rows:
        by_resolver.setdefault(r.resolver, []).append(r)
    out: list[DnsCompareRow] = []
    for resolver, samples in by_resolver.items():
        oks = [s.query_ms for s in samples if s.ok and s.query_ms is not None]
        fails = sum(1 for s in samples if not s.ok)
        out.append(DnsCompareRow(
            resolver=resolver, n=len(samples),
            median_ms=percentile(oks, 50) if oks else None,
            p95_ms=percentile(oks, 95) if oks else None,
            jitter_ms=(percentile(oks, 75) - percentile(oks, 25)) if oks else None,
            fail_pct=round(100 * fails / len(samples), 1) if samples else 0.0,
        ))
    out.sort(key=lambda r: r.median_ms if r.median_ms is not None else 1e9)
    return out


def experience(session: Session, window: int, network_id: int | None) -> ExperienceOut:
    """What the connection feels like for calls / browsing / streaming / gaming — plain-language
    ratings backed by the metrics we already measure."""
    now = time.time()
    start = now - window
    hosts = _internet_hosts()
    pings = session.scalars(
        select(PingRaw).where(
            PingRaw.ts >= start, PingRaw.target.in_(hosts), *_scope(PingRaw.network_id, network_id)
        )
    ).all()
    pings = _drop_measurement_artifacts(session, pings, start, network_id)
    jitters = [p.jitter for p in pings if p.jitter is not None]
    per_target: dict[str, list[float]] = {}
    per_target_rtt: dict[str, list[float]] = {}
    for p in pings:
        per_target.setdefault(p.target, []).append(p.loss_pct)
        if p.rtt_avg is not None:
            per_target_rtt.setdefault(p.target, []).append(p.rtt_avg)
    typical_loss = (
        percentile([sum(v) / len(v) for v in per_target.values()], 50) if per_target else None
    )
    # representative internet RTT: median across targets (not pooled — audit H1)
    rtt_repr = (
        percentile([percentile(v, 50) for v in per_target_rtt.values()], 50)
        if per_target_rtt
        else None
    )
    active = session.scalars(
        select(ActiveTest)
        .where(*_scope(ActiveTest.network_id, network_id))
        .order_by(ActiveTest.ts.desc())
        .limit(1)
    ).first()
    dns = session.scalars(
        select(DnsRaw).where(
            DnsRaw.ts >= start, DnsRaw.ok, DnsRaw.query_ms.is_not(None),
            *_scope(DnsRaw.network_id, network_id),
        )
    ).all()
    dns_ms = percentile([d.query_ms for d in dns if d.query_ms is not None], 50) if dns else None

    inputs = ExperienceInputs(
        rtt_ms=rtt_repr,
        loss_pct=typical_loss,
        jitter_ms=percentile(jitters, 95) if jitters else None,
        bufferbloat_ms=active.bufferbloat_ms if active else None,
        download_mbps=active.download_mbps if active else None,
        upload_mbps=active.upload_mbps if active else None,
        dns_ms=dns_ms,
    )
    return ExperienceOut(activities=[
        ActivityOut(
            activity=v.activity, rating=v.rating, summary=v.summary,
            metrics=[
                MetricOut(label=m.label, value=m.value, unit=m.unit, ok=m.ok) for m in v.metrics
            ],
        )
        for v in assess(inputs)
    ])


def diurnal(
    session: Session, metric: str, window: int, network_id: int | None
) -> DiurnalResponse:
    """Per-hour-of-day distribution of loss or latency over internet targets, with CIs and an
    honest days-observed flag (a diurnal claim needs the pattern to repeat across days). Reads the
    1-h rollups (retained for months), so the ≥3-day pattern can actually be met — raw is pruned
    at ~48 h and could never satisfy it."""
    start = time.time() - window
    agg_metric = "ping.rtt_avg" if metric == "latency" else "ping.loss_pct"
    hosts = _internet_hosts()
    rows = session.scalars(
        select(Agg).where(
            Agg.metric == agg_metric, Agg.resolution == "1h", Agg.bucket >= start,
            Agg.tag.in_(hosts), *_scope(Agg.network_id, network_id),
        )
    ).all()
    samples = [(r.bucket, r.avg) for r in rows if r.avg is not None]
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
    # "to the internet" must mean the internet, not the ~1 ms LAN gateway; and a representative
    # (median) value, not the single most-optimistic target.
    internet_hosts = _internet_hosts()
    internet = [r for r in recent if r.target in internet_hosts]
    reachable = [r for r in internet if r.loss_pct < 100 and r.rtt_avg is not None]
    net_rtts = [r.rtt_avg for r in reachable if r.rtt_avg is not None]
    current_rtt = percentile(net_rtts, 50) if net_rtts else None
    current_loss = percentile([r.loss_pct for r in internet], 50) if internet else None

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
    heartbeat = session.get(State, "collector_heartbeat")
    collector_healthy = heartbeat is not None and now - float(heartbeat.value) < 30
    latest_tput = session.scalars(
        select(ThroughputRaw)
        .where(ThroughputRaw.ts >= now - 30, *_scope(ThroughputRaw.network_id, network_id))
        .order_by(ThroughputRaw.ts.desc())
        .limit(1)
    ).first()

    return Status(
        online=bool(reachable),
        current_rtt=current_rtt,
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
        current_rx_mbps=latest_tput.rx_bps / 1e6 if latest_tput else None,
        current_tx_mbps=latest_tput.tx_bps / 1e6 if latest_tput else None,
        collector_healthy=collector_healthy,
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
    # Loss/latency/coverage read RAW ping rows, which are pruned at `raw_hours`; a 7-day request
    # therefore only has ~48 h of data. Cap the window to what raw retention can actually cover so
    # availability (downtime / covered) and coverage% aren't computed against absent time.
    window = min(window, get_config().retention.raw_hours * 3600)
    start = now - window
    hosts = _internet_hosts()

    pings = session.scalars(
        select(PingRaw).where(
            PingRaw.ts >= start, PingRaw.target.in_(hosts), *_scope(PingRaw.network_id, network_id)
        )
    ).all()
    pings = _drop_measurement_artifacts(session, pings, start, network_id)
    jitters = [p.jitter for p in pings if p.jitter is not None]

    per_target: dict[str, list[float]] = {}
    for p in pings:
        per_target.setdefault(p.target, []).append(p.loss_pct)
    worst_target, typical_loss, loss_ci, loss_burst = _loss_stats(per_target)

    latency_p95, latency_excess = _latency_stats(pings)

    outages = session.scalars(
        select(Event).where(
            Event.kind == "outage", Event.ts >= start, *_scope(Event.network_id, network_id)
        )
    ).all()
    downtime = sum((o.end_ts or now) - max(o.ts, start) for o in outages)
    worst_outage = max(((o.end_ts or now) - o.ts for o in outages), default=None)
    worst_cause = max(outages, key=lambda o: (o.end_ts or now) - o.ts).detail if outages else None
    outages_isp = sum(1 for o in outages if o.detail == "isp")
    # Only count time we actually sampled: an overnight suspend leaves a gap that must NOT be
    # read as uptime, or availability (and any before/after comparison) is silently inflated.
    covered = covered_seconds([p.ts for p in pings], _COVERAGE_MAX_GAP)
    coverage_pct = 100 * covered / window if window else None

    wifi = session.scalars(
        select(WifiRaw).where(WifiRaw.ts >= start, *_scope(WifiRaw.network_id, network_id))
    ).all()
    signals = [w.signal_dbm for w in wifi if w.signal_dbm is not None]
    latest_wifi = wifi[-1] if wifi else None
    power_save = latest_wifi.power_save if latest_wifi else None
    channel_advice = _channel_advice(session, latest_wifi, start, network_id)
    channel_series = [(w.ts, _freq_to_channel(w.freq)) for w in wifi]
    current_channel = _freq_to_channel(latest_wifi.freq) if latest_wifi else None
    hours_on_channel = channel_continuous_hours(channel_series, current_channel)
    client_outages = _client_initiated_outages(session, outages, start, network_id)

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

    anycast_out, regional_pct, regional_user_rtt, bgp_updates, bgp_stable = _outside_in(
        session, start, network_id
    )
    signal_avg = sum(signals) / len(signals) if signals else None
    corr = _loss_retry_corr(session, hosts, start, network_id)
    # Attribute on the REPRESENTATIVE path (median loss among internet targets), not the first one
    # in config — otherwise a single badly-peered target defines "the ISP path is lossy" when the
    # typical path is clean.
    primary = _representative_target(get_config().targets, per_target)
    hops = hop_stats(session, primary, start, network_id) if primary else []
    attribution = attribute(hops, corr, wifi_weak=signal_avg is not None and signal_avg <= -72)

    # Segment split from RELIABLE end-to-end RTTs (not hop RTTs): the best-peered path's median
    # is the access proxy, the worst path's median is the destination.
    per_target_rtt: dict[str, list[float]] = {}
    for p in pings:
        if p.rtt_avg is not None:
            per_target_rtt.setdefault(p.target, []).append(p.rtt_avg)
    medians = [percentile(v, 50) for v in per_target_rtt.values() if v]
    segment = segment_classify(min(medians), max(medians)) if medians else None

    return WindowStats(
        loss=typical_loss,
        typical_loss=typical_loss,
        loss_ci=loss_ci,
        loss_burst_len=loss_burst,
        latency=latency_p95,
        latency_excess=latency_excess,
        jitter=percentile(jitters, 95) if jitters else None,
        bufferbloat=latest_active.bufferbloat_ms if latest_active else None,
        availability=max(0.0, 100 * (1 - downtime / covered)) if covered else None,
        coverage_pct=coverage_pct,
        outage_count=len(outages),
        downtime_s=downtime,
        worst_outage_s=worst_outage,
        worst_outage_cause=worst_cause,
        worst_target=worst_target,
        wifi_signal_avg=signal_avg,
        wifi_power_save=power_save,
        channel_advice=channel_advice,
        hours_on_channel=hours_on_channel,
        outages_client_initiated=client_outages,
        outages_isp=outages_isp,
        dns_fail=dns_fail,
        dns_total=len(dns),
        attribution=attribution,
        segment=segment,
        loss_retry_corr=corr,
        anycast_out=anycast_out,
        regional_pct=regional_pct,
        regional_user_rtt=regional_user_rtt,
        bgp_updates=bgp_updates,
        bgp_stable=bgp_stable,
        window_label=window_label,
    )


def _drop_measurement_artifacts(
    session: Session, pings: Sequence[PingRaw], start: float, network_id: int | None
) -> list[PingRaw]:
    """Remove ping samples the tool's OWN activity perturbed, so the connection isn't graded on
    self-induced noise: (a) WiFi neighbour-scans take the radio off-channel and spike every target
    (the gateway included) at once; (b) the periodic speedtest saturates the link and induces the
    bufferbloat/loss it would then penalise. The scan/speedtest data themselves are untouched."""
    scan_ts = session.scalars(
        select(WifiScan.ts).where(
            WifiScan.ts >= start - _SCAN_GUARD, *_scope(WifiScan.network_id, network_id)
        )
    ).all()
    active_ts = session.scalars(
        select(ActiveTest.ts).where(
            ActiveTest.ts >= start - _SPEEDTEST_AFTER, *_scope(ActiveTest.network_id, network_id)
        )
    ).all()
    if not scan_ts and not active_ts:
        return list(pings)
    blocked = blocked_seconds(list(scan_ts), _SCAN_GUARD)
    for t in active_ts:  # a speedtest saturates from its start ts for ~tens of seconds
        blocked.update(range(int(t) - _SPEEDTEST_BEFORE, int(t) + _SPEEDTEST_AFTER + 1))
    return [p for p in pings if int(p.ts) not in blocked]


def _latency_stats(pings: Sequence[PingRaw]) -> tuple[float | None, float | None]:
    """Representative internet latency: per-target p95 RTT and per-target excess over THAT target's
    own floor, aggregated by median across targets. Pooling all targets would let a distant-but-
    healthy host's tail (and the nearest host's floor) masquerade as congestion (audit H1)."""
    by_rtt: dict[str, list[float]] = {}
    by_floor: dict[str, list[float]] = {}
    for p in pings:
        if p.rtt_avg is not None:
            by_rtt.setdefault(p.target, []).append(p.rtt_avg)
        if p.rtt_min is not None:
            by_floor.setdefault(p.target, []).append(p.rtt_min)
    if not by_rtt:
        return (None, None)
    latency_p95 = percentile([percentile(v, 95) for v in by_rtt.values()], 50)
    excesses = [
        max(0.0, percentile(rtts, 95) - min(by_floor[t]))
        for t, rtts in by_rtt.items()
        if by_floor.get(t)
    ]
    latency_excess = percentile(excesses, 50) if excesses else None
    return (latency_p95, latency_excess)


def _loss_stats(
    per_target: dict[str, list[float]],
) -> tuple[tuple[str, float] | None, float | None, tuple[float, float] | None, float | None]:
    """From per-target loss samples: the worst target (host, avg%), the TYPICAL destination's
    AVERAGE loss (median across targets — so one badly-peered CDN can't define the grade, and the
    convex score curve is fed the mean it's calibrated for, not a p95 of quantized per-cycle loss
    that steps straight to F), the block-bootstrap CI on the worst path, and its burst length."""
    if not per_target:
        return (None, None, None, None)
    host, vals = max(per_target.items(), key=lambda kv: sum(kv[1]) / len(kv[1]))
    worst_target = (host, sum(vals) / len(vals))
    avg_by_target = {h: sum(v) / len(v) for h, v in per_target.items()}
    typical_loss = percentile(list(avg_by_target.values()), 50)
    loss_ci = block_bootstrap_ci(vals) if len(vals) > 10 else None
    _, loss_burst = gilbert_elliott([v > 0 for v in vals])
    return (worst_target, typical_loss, loss_ci, loss_burst)


def _representative_target(targets: list[Target], per_target: dict[str, list[float]]) -> str | None:
    """The internet/site target whose average loss is the median — the path a typical connection
    takes. Falls back to the first internet target when there's no loss data yet."""
    candidates = [t.host for t in targets if t.kind in ("internet", "site")]
    with_data = sorted(
        (h for h in candidates if per_target.get(h)),
        key=lambda h: sum(per_target[h]) / len(per_target[h]),
    )
    if with_data:
        return with_data[len(with_data) // 2]
    return candidates[0] if candidates else None


def _regional_percentile(session: Session) -> tuple[float | None, float | None]:
    """Where our own RTT to the reference target sits within the region's RIPE Atlas probes."""
    baseline = session.scalars(
        select(RegionalBaseline).order_by(RegionalBaseline.ts.desc()).limit(1)
    ).first()
    user = session.get(State, "kroot_rtt")
    if baseline is None or user is None:
        return (None, None)
    user_rtt = float(user.value)
    values = json.loads(baseline.values_json)
    return (percentile_rank(user_rtt, values), user_rtt)


def _freq_to_channel(freq: int | None) -> int | None:
    if freq is None:
        return None
    if freq >= 5000:
        return (freq - 5000) // 5
    return (freq - 2407) // 5  # 2.4 GHz


def _channel_advice(
    session: Session, latest_wifi: WifiRaw | None, start: float, network_id: int | None
) -> ChannelAdvice | None:
    current = _freq_to_channel(latest_wifi.freq) if latest_wifi else None
    # Count DISTINCT APs (BSSID) per channel over the last 30 min — robust to a single partial
    # nmcli scan; one snapshot can miss most neighbours.
    window = max(start, time.time() - 1800)
    scans = session.scalars(
        select(WifiScan).where(WifiScan.ts >= window, *_scope(WifiScan.network_id, network_id))
    ).all()
    if not scans:
        return None
    own_bssid = latest_wifi.bssid if latest_wifi else None
    by_channel: dict[int, set[str | None]] = {}
    for sc in scans:
        if sc.bssid == own_bssid:  # don't count our own AP as congestion in our own block
            continue
        by_channel.setdefault(sc.channel, set()).add(sc.bssid)
    channels = [ch for ch, bssids in by_channel.items() for _ in bssids]
    return analyze_channel(current, channels)


def _client_initiated_outages(
    session: Session, outages: Sequence[Event], start: float, network_id: int | None
) -> int:
    """How many outage windows coincide with a client-initiated (locally-generated) WiFi
    disconnect — i.e. the laptop suspending/power-saving, not the network failing."""
    disconnects = session.scalars(
        select(Event).where(
            Event.kind == "wifi_disconnect", Event.detail.like("%local%"),
            Event.ts >= start - 30, *_scope(Event.network_id, network_id),
        )
    ).all()
    dts = [d.ts for d in disconnects]
    return sum(1 for o in outages if any(abs(o.ts - dt) <= 30 for dt in dts))


def _outside_in(
    session: Session, start: float, network_id: int | None
) -> tuple[list[tuple[str, str, str]], float | None, float | None, int | None, bool | None]:
    """The outside-in corroboration: out-of-country POPs, regional percentile, BGP stability."""
    anycast_out = _anycast_out_of_country(session, start, network_id)
    regional_pct, regional_user_rtt = _regional_percentile(session)
    bgp_state = session.get(State, "bgp_updates")
    bgp_stable_state = session.get(State, "bgp_stable")
    bgp_updates = int(bgp_state.value) if bgp_state else None
    bgp_stable = (bgp_stable_state.value == "1") if bgp_stable_state else None
    return anycast_out, regional_pct, regional_user_rtt, bgp_updates, bgp_stable


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

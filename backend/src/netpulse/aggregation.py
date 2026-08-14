"""Downsampling + retention.

Raw samples roll up into 5-minute then 1-hour :class:`Agg` buckets so the 24h/7d views read
a handful of rows instead of thousands. Each run recomputes a bounded recent window
idempotently (delete-then-insert the affected buckets), then prunes old rows per retention.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from netpulse.config import Retention
from netpulse.db.base import Base
from netpulse.db.models import (
    Agg,
    AnycastPop,
    DnsRaw,
    Flow,
    FlowQuality,
    HopLocation,
    PingRaw,
    TcpConnect,
    ThroughputRaw,
    Traceroute,
    WifiRaw,
    WifiScan,
)
from netpulse.quality import percentile

_5M = 300
_1H = 3600


@dataclass(frozen=True, slots=True)
class MetricSource:
    """A raw column to roll up. ``tag_attr`` splits series (per target/resolver)."""

    name: str
    model: type[Base]
    value_attr: str
    tag_attr: str | None = None


SOURCES: tuple[MetricSource, ...] = (
    MetricSource("ping.rtt_avg", PingRaw, "rtt_avg", "target"),
    MetricSource("ping.loss_pct", PingRaw, "loss_pct", "target"),
    MetricSource("ping.jitter", PingRaw, "jitter", "target"),
    MetricSource("wifi.signal_dbm", WifiRaw, "signal_dbm"),
    MetricSource("wifi.tx_bitrate", WifiRaw, "tx_bitrate"),
    # tx_retries is a cumulative counter; averaging it as a series is meaningless (it only ever
    # rises and resets on reconnect). The loss/retry *correlation* uses per-bucket deltas instead.
    MetricSource("throughput.rx_bps", ThroughputRaw, "rx_bps"),
    MetricSource("throughput.tx_bps", ThroughputRaw, "tx_bps"),
    MetricSource("dns.query_ms", DnsRaw, "query_ms", "resolver"),
)


def _bucket(ts: float, width: int) -> float:
    return (int(ts) // width) * width


# group key: (bucket start, network_id, tag)
GroupKey = tuple[float, int | None, str]


def _summarize(key: GroupKey, resolution: str, metric: str, values: list[float]) -> Agg:
    bucket, network_id, tag = key
    return Agg(
        bucket=bucket, network_id=network_id, resolution=resolution, metric=metric, tag=tag,
        avg=sum(values) / len(values), mn=min(values), mx=max(values),
        p95=percentile(values, 95), n=len(values),
    )


def _rollup_raw_to_5m(session: Session, source: MetricSource, since: float) -> None:
    model = source.model
    rows: Sequence[Base] = session.scalars(
        select(model).where(model.ts >= since)  # type: ignore[attr-defined]
    ).all()

    grouped: dict[GroupKey, list[float]] = {}
    for row in rows:
        value = getattr(row, source.value_attr)
        if value is None:
            continue
        tag = getattr(row, source.tag_attr) if source.tag_attr else ""
        key = (_bucket(row.ts, _5M), row.network_id, tag)  # type: ignore[attr-defined]
        grouped.setdefault(key, []).append(value)

    _replace_buckets(session, "5m", source.name, since, grouped)


def _rollup_5m_to_1h(session: Session, source: MetricSource, since: float) -> None:
    rows = session.scalars(
        select(Agg).where(
            Agg.resolution == "5m", Agg.metric == source.name, Agg.bucket >= since
        )
    ).all()

    grouped: dict[GroupKey, list[Agg]] = {}
    for row in rows:
        if row.avg is None:
            continue
        grouped.setdefault((_bucket(row.bucket, _1H), row.network_id, row.tag), []).append(row)

    session.execute(
        delete(Agg).where(
            Agg.resolution == "1h", Agg.metric == source.name, Agg.bucket >= since
        )
    )
    for (bucket, network_id, tag), aggs in grouped.items():
        session.add(_combine_aggs(bucket, network_id, tag, source.name, aggs))


def _combine_aggs(
    bucket: float, network_id: int | None, tag: str, metric: str, aggs: list[Agg]
) -> Agg:
    """Roll 5-min aggregates into a 1-h one WITHOUT collapsing to a mean-of-means.

    min/max carry up exactly; avg is sample-count weighted; n is the true underlying sample
    count. p95 does not compose, so it is estimated as the max of the 5-min p95s — a defensible
    'typical worst-5-min tail' that preserves the spike, instead of the p95 of the averages
    (which smooths the tail away and understates the 7d view).
    """
    total_n = sum(a.n for a in aggs) or 1
    mns = [a.mn for a in aggs if a.mn is not None]
    mxs = [a.mx for a in aggs if a.mx is not None]
    p95s = [a.p95 for a in aggs if a.p95 is not None]
    return Agg(
        bucket=bucket, network_id=network_id, resolution="1h", metric=metric, tag=tag,
        avg=sum((a.avg or 0.0) * a.n for a in aggs) / total_n,
        mn=min(mns) if mns else None,
        mx=max(mxs) if mxs else None,
        p95=max(p95s) if p95s else None,
        n=sum(a.n for a in aggs),
    )


def _replace_buckets(
    session: Session,
    resolution: str,
    metric: str,
    since: float,
    grouped: dict[GroupKey, list[float]],
) -> None:
    session.execute(
        delete(Agg).where(
            Agg.resolution == resolution, Agg.metric == metric, Agg.bucket >= since
        )
    )
    for key, values in grouped.items():
        session.add(_summarize(key, resolution, metric, values))


def run_rollups(session: Session, retention: Retention, now: float) -> None:
    since_5m = now - 2 * _1H
    since_1h = now - 26 * _1H
    for source in SOURCES:
        _rollup_raw_to_5m(session, source, since_5m)
        _rollup_5m_to_1h(session, source, since_1h)
    _prune(session, retention, now)
    session.commit()


def _prune(session: Session, retention: Retention, now: float) -> None:
    raw_cutoff = now - retention.raw_hours * _1H
    for model in (PingRaw, WifiRaw, ThroughputRaw, DnsRaw):
        session.execute(delete(model).where(model.ts < raw_cutoff))
    # High-volume append-only tables the rollup doesn't cover — bound them so an always-on daemon
    # can't grow the DB (and the Python-side window scans) without limit. Event/ActiveTest are kept
    # (low-volume outage/speedtest evidence) and RegionalBaseline is tiny.
    txn_cutoff = now - retention.transactional_days * 86400
    for txn in (Traceroute, Flow, FlowQuality, WifiScan, TcpConnect, AnycastPop, HopLocation):
        session.execute(delete(txn).where(txn.ts < txn_cutoff))
    session.execute(
        delete(Agg).where(Agg.resolution == "5m", Agg.bucket < now - retention.agg5m_days * 86400)
    )
    session.execute(
        delete(Agg).where(Agg.resolution == "1h", Agg.bucket < now - retention.agg1h_days * 86400)
    )

"""SQLAlchemy 2.0 models — the time-series store.

One table per probe (raw samples), a generic :class:`Agg` for downsampled rollups, and
operational tables (:class:`Event`, :class:`State`, :class:`Network`). Raw tables are
append-only and pruned by retention; ``Agg`` holds 5-min and 1-h buckets so the 7d view
stays fast. Every sample is tagged with the :class:`Network` it was taken on, so analysis is
per-network (the PC moves between home / office / café).
"""

from __future__ import annotations

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from netpulse.db.base import Base, ts_column


class Network(Base):
    """A distinct network the PC has used, identified by a stable fingerprint."""

    __tablename__ = "network"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String, unique=True, index=True)  # fingerprint
    ssid: Mapped[str | None] = mapped_column(String)
    bssid: Mapped[str | None] = mapped_column(String)
    gateway_ip: Mapped[str | None] = mapped_column(String)
    gateway_mac: Mapped[str | None] = mapped_column(String)
    interface: Mapped[str | None] = mapped_column(String)
    label: Mapped[str | None] = mapped_column(String)  # user-editable ("Home", "Office")
    first_seen: Mapped[float] = mapped_column(Float)
    last_seen: Mapped[float] = mapped_column(Float)


class NetworkScoped:
    """Mixin: tag a row with the network it was sampled on (nullable for pre-migration rows)."""

    network_id: Mapped[int | None] = mapped_column(
        ForeignKey("network.id"), index=True, default=None
    )


class PingRaw(NetworkScoped, Base):
    __tablename__ = "ping_raw"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[float] = ts_column()
    target: Mapped[str] = mapped_column(String, index=True)
    loss_pct: Mapped[float] = mapped_column(Float)
    rtt_min: Mapped[float | None] = mapped_column(Float)
    rtt_avg: Mapped[float | None] = mapped_column(Float)
    rtt_max: Mapped[float | None] = mapped_column(Float)
    jitter: Mapped[float | None] = mapped_column(Float)  # mdev


class WifiRaw(NetworkScoped, Base):
    __tablename__ = "wifi_raw"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[float] = ts_column()
    ssid: Mapped[str | None] = mapped_column(String)
    bssid: Mapped[str | None] = mapped_column(String)  # AP MAC — a change means roaming
    freq: Mapped[int | None] = mapped_column(Integer)
    signal_dbm: Mapped[float | None] = mapped_column(Float)
    noise_dbm: Mapped[float | None] = mapped_column(Float)
    tx_bitrate: Mapped[float | None] = mapped_column(Float)
    rx_bitrate: Mapped[float | None] = mapped_column(Float)
    tx_retries: Mapped[int | None] = mapped_column(Integer)
    tx_failed: Mapped[int | None] = mapped_column(Integer)


class ThroughputRaw(NetworkScoped, Base):
    __tablename__ = "throughput_raw"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[float] = ts_column()
    rx_bps: Mapped[float] = mapped_column(Float)
    tx_bps: Mapped[float] = mapped_column(Float)


class DnsRaw(NetworkScoped, Base):
    __tablename__ = "dns_raw"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[float] = ts_column()
    domain: Mapped[str] = mapped_column(String, index=True)
    resolver: Mapped[str] = mapped_column(String, index=True)
    query_ms: Mapped[float | None] = mapped_column(Float)
    ok: Mapped[bool] = mapped_column(Boolean)


class Agg(NetworkScoped, Base):
    """Generic downsampled rollup: one row per (network, bucket, resolution, metric, tag)."""

    __tablename__ = "agg"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bucket: Mapped[float] = ts_column()  # bucket start, epoch seconds
    resolution: Mapped[str] = mapped_column(String, index=True)  # "5m" | "1h"
    metric: Mapped[str] = mapped_column(String, index=True)  # "ping.rtt_avg", "wifi.signal_dbm"…
    tag: Mapped[str] = mapped_column(String, index=True, default="")  # target / resolver / ""
    avg: Mapped[float | None] = mapped_column(Float)
    mn: Mapped[float | None] = mapped_column(Float)
    mx: Mapped[float | None] = mapped_column(Float)
    p95: Mapped[float | None] = mapped_column(Float)
    n: Mapped[int] = mapped_column(Integer)


class ActiveTest(NetworkScoped, Base):
    __tablename__ = "active_test"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[float] = ts_column()
    download_mbps: Mapped[float | None] = mapped_column(Float)
    upload_mbps: Mapped[float | None] = mapped_column(Float)
    idle_latency: Mapped[float | None] = mapped_column(Float)
    down_latency: Mapped[float | None] = mapped_column(Float)  # loaded (download)
    up_latency: Mapped[float | None] = mapped_column(Float)  # loaded (upload)
    bufferbloat_ms: Mapped[float | None] = mapped_column(Float)
    grade: Mapped[str | None] = mapped_column(String)
    mos: Mapped[float | None] = mapped_column(Float)


class Traceroute(NetworkScoped, Base):
    __tablename__ = "traceroute"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[float] = ts_column()
    target: Mapped[str] = mapped_column(String, index=True)
    hop: Mapped[int] = mapped_column(Integer)
    host: Mapped[str | None] = mapped_column(String)
    loss_pct: Mapped[float | None] = mapped_column(Float)
    rtt_ms: Mapped[float | None] = mapped_column(Float)


class Flow(NetworkScoped, Base):
    __tablename__ = "flow"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[float] = ts_column()
    remote_ip: Mapped[str] = mapped_column(String, index=True)
    rdns: Mapped[str | None] = mapped_column(String)
    asn: Mapped[str | None] = mapped_column(String)
    app: Mapped[str | None] = mapped_column(String, index=True)  # classified service
    conns: Mapped[int] = mapped_column(Integer)


class WifiScan(NetworkScoped, Base):
    __tablename__ = "wifi_scan"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[float] = ts_column()
    channel: Mapped[int] = mapped_column(Integer, index=True)
    signal_dbm: Mapped[float] = mapped_column(Float)
    ssid: Mapped[str | None] = mapped_column(String)
    bssid: Mapped[str | None] = mapped_column(String)


class Event(NetworkScoped, Base):
    """Discrete events: outages, roaming, DNS failures, IP/network changes, alerts."""

    __tablename__ = "event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[float] = ts_column()
    end_ts: Mapped[float | None] = mapped_column(Float)  # None while ongoing
    kind: Mapped[str] = mapped_column(String, index=True)  # "outage"|"roam"|"dns"|"network"…
    severity: Mapped[str] = mapped_column(String)  # "info" | "warning" | "error"
    detail: Mapped[str] = mapped_column(String)


class State(Base):
    """Key/value scratch for the collector (last counters, open events, public IP)."""

    __tablename__ = "state"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String)

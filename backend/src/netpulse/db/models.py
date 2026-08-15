"""SQLAlchemy 2.0 models — the time-series store.

One table per probe (raw samples), a generic :class:`Agg` for downsampled rollups, and
operational tables (:class:`Event`, :class:`State`, :class:`Network`). Raw tables are
append-only and pruned by retention; ``Agg`` holds 5-min and 1-h buckets so the 7d view
stays fast. Every sample is tagged with the :class:`Network` it was taken on, so analysis is
per-network (the PC moves between home / office / café).
"""

from __future__ import annotations

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String
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
    __table_args__ = (Index("ix_ping_scope_ts", "network_id", "target", "ts"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[float] = ts_column()
    target: Mapped[str] = mapped_column(String, index=True)
    af: Mapped[str] = mapped_column(String, default="4")  # address family: "4" | "6"
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
    width_mhz: Mapped[int | None] = mapped_column(Integer)  # 20/40/80/160 — wider = more contention
    signal_dbm: Mapped[float | None] = mapped_column(Float)
    noise_dbm: Mapped[float | None] = mapped_column(Float)
    airtime_busy_pct: Mapped[float | None] = mapped_column(Float)  # channel occupancy from survey
    airtime_foreign_pct: Mapped[float | None] = mapped_column(Float)  # busy minus our own rx/tx
    tx_bitrate: Mapped[float | None] = mapped_column(Float)
    rx_bitrate: Mapped[float | None] = mapped_column(Float)
    tx_packets: Mapped[int | None] = mapped_column(Integer)  # cumulative; for retry-rate ratios
    tx_retries: Mapped[int | None] = mapped_column(Integer)
    tx_failed: Mapped[int | None] = mapped_column(Integer)
    power_save: Mapped[bool | None] = mapped_column(Boolean)  # on = a common cause of drops


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
    __table_args__ = (Index("ix_agg_lookup", "metric", "resolution", "network_id", "bucket"),)

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
    __table_args__ = (Index("ix_traceroute_scope_ts", "network_id", "target", "ts"),)

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


class TcpConnect(NetworkScoped, Base):
    """Active TCP-handshake latency (SYN→SYN/ACK) — the app-relevant, non-ICMP-deprioritized
    latency signal; also traverses hosts that filter ICMP. status: ok | refused | filtered."""

    __tablename__ = "tcp_connect"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[float] = ts_column()
    target: Mapped[str] = mapped_column(String, index=True)
    port: Mapped[int] = mapped_column(Integer)
    connect_ms: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String)


class FlowQuality(NetworkScoped, Base):
    """Passive per-endpoint transport quality from the kernel (`ss -ti`).

    Real RTT / base-RTT / retransmissions / goodput on the destinations the user *actually*
    uses — app experience, not synthetic ICMP to a curated list. Aggregated per remote endpoint.
    """

    __tablename__ = "flow_quality"
    __table_args__ = (Index("ix_flow_quality_scope_ts", "network_id", "ts"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[float] = ts_column()
    remote_ip: Mapped[str] = mapped_column(String, index=True)
    asn: Mapped[str | None] = mapped_column(String)
    app: Mapped[str | None] = mapped_column(String, index=True)
    srtt_ms: Mapped[float | None] = mapped_column(Float)  # smoothed RTT
    min_rtt_ms: Mapped[float | None] = mapped_column(Float)  # base RTT (congestion-free floor)
    retrans_total: Mapped[int | None] = mapped_column(Integer)  # cumulative retransmits
    delivery_mbps: Mapped[float | None] = mapped_column(Float)  # achieved goodput
    sockets: Mapped[int] = mapped_column(Integer)  # sockets aggregated


class AnycastPop(NetworkScoped, Base):
    """Which POP an anycast CDN is serving this host from — the actionable routing signal.

    Cloudflare's ``cdn-cgi/trace`` reports the serving ``colo`` (airport). If that airport is
    out-of-country while the CDN operates in-country POPs, the ISP is routing you the long way.
    """

    __tablename__ = "anycast_pop"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[float] = ts_column()
    provider: Mapped[str] = mapped_column(String, index=True)  # "cloudflare"
    target: Mapped[str] = mapped_column(String)  # the anycast IP probed
    colo: Mapped[str | None] = mapped_column(String)  # serving POP airport code
    colo_country: Mapped[str | None] = mapped_column(String)  # POP country (from IATA table)
    client_country: Mapped[str | None] = mapped_column(String)  # your country (loc=)
    out_of_country: Mapped[bool] = mapped_column(Boolean)


class RegionalBaseline(Base):
    """Cached outside-in reference distribution (e.g. RIPE Atlas MX probes' RTT to a target),
    so the tool can say 'worse than X% of comparable connections' instead of branding regional
    reality a fault. Refreshed on a slow cadence; degrades gracefully to inside-out when absent."""

    __tablename__ = "regional_baseline"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[float] = ts_column()
    source: Mapped[str] = mapped_column(String)  # "ripe_atlas"
    target: Mapped[str] = mapped_column(String, index=True)
    country: Mapped[str] = mapped_column(String)
    metric: Mapped[str] = mapped_column(String)  # "rtt_ms"
    values_json: Mapped[str] = mapped_column(String)  # JSON list of floats
    n: Mapped[int] = mapped_column(Integer)


class MediaRaw(NetworkScoped, Base):
    """Live real-time (UDP/QUIC) media-path quality. `ss` gives no RTT for UDP, so when an active
    UDP media flow exists we ping its actual remote peer — that ICMP RTT/loss/jitter IS the path a
    call/game rides, the metric the TCP-only flow probe is blind to."""

    __tablename__ = "media_raw"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[float] = ts_column()
    remote_ip: Mapped[str] = mapped_column(String)
    app: Mapped[str | None] = mapped_column(String)
    endpoints: Mapped[int] = mapped_column(Integer)  # active UDP flows to this peer
    rtt_ms: Mapped[float | None] = mapped_column(Float)
    loss_pct: Mapped[float | None] = mapped_column(Float)
    jitter_ms: Mapped[float | None] = mapped_column(Float)


class State(Base):
    """Key/value scratch for the collector (last counters, open events, public IP)."""

    __tablename__ = "state"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String)


class HopLocation(Base):
    """Cached geolocation of a traceroute hop IP (RIPEstat), so the map can draw the real route
    without re-querying. Private/unlocatable IPs are cached as located=False to avoid retries."""

    __tablename__ = "hop_location"

    ip: Mapped[str] = mapped_column(String, primary_key=True)
    ts: Mapped[float] = ts_column()
    located: Mapped[bool] = mapped_column(Boolean)
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    city: Mapped[str | None] = mapped_column(String)
    country: Mapped[str | None] = mapped_column(String)

"""Pydantic response models for the JSON API."""

from __future__ import annotations

from pydantic import BaseModel

Range = str  # "6h" | "24h" | "7d" (validated in the router)


class Point(BaseModel):
    ts: float
    avg: float | None
    mn: float | None = None
    mx: float | None = None
    p95: float | None = None


class Series(BaseModel):
    tag: str
    points: list[Point]


class SeriesResponse(BaseModel):
    metric: str
    range: Range
    resolution: str
    series: list[Series]


class ActivePoint(BaseModel):
    ts: float
    download_mbps: float | None
    upload_mbps: float | None
    idle_latency: float | None
    bufferbloat_ms: float | None
    grade: str | None
    mos: float | None


class EventOut(BaseModel):
    ts: float
    end_ts: float | None
    kind: str
    severity: str
    detail: str
    duration: float | None


class FlowOut(BaseModel):
    remote_ip: str
    rdns: str | None
    asn: str | None
    app: str | None
    conns: int


class NetworkOut(BaseModel):
    id: int
    label: str | None
    ssid: str | None
    gateway_ip: str | None
    gateway_mac: str | None
    interface: str | None
    first_seen: float
    last_seen: float
    is_current: bool


class ScoreOut(BaseModel):
    score: float
    grade: str
    breakdown: dict[str, float]


class FindingOut(BaseModel):
    severity: str
    title: str
    detail: str


class VerdictOut(BaseModel):
    score: ScoreOut
    headline: str
    findings: list[FindingOut]


class RawAgg(BaseModel):
    column: str
    count: int
    min: float | None
    max: float | None
    avg: float | None
    p95: float | None


class RawColumn(BaseModel):
    name: str
    type: str  # "number" | "string" | "bool" | "time"
    unit: str | None
    values: list[str] | None  # distinct values for enum-style string columns (for filters)


class RawPage(BaseModel):
    columns: list[RawColumn]
    rows: list[dict[str, object]]
    total: int
    agg: list[RawAgg]


class HopPoint(BaseModel):
    ts: float
    loss_pct: float | None
    rtt_ms: float | None


class HopSeries(BaseModel):
    hop: int
    host: str | None
    avg_loss: float
    points: list[HopPoint]


class HopTimeline(BaseModel):
    target: str
    hops: list[HopSeries]


class AnycastOut(BaseModel):
    provider: str
    target: str
    colo: str | None
    colo_country: str | None
    client_country: str | None
    out_of_country: bool
    ts: float


class FlowQualityOut(BaseModel):
    remote_ip: str
    asn: str | None
    app: str | None
    srtt_ms: float | None
    min_rtt_ms: float | None
    excess_ms: float | None  # srtt - min_rtt = current queuing/congestion
    retrans_total: int | None
    delivery_mbps: float | None
    sockets: int


class DiurnalCell(BaseModel):
    hour: int
    mean: float
    ci_lo: float
    ci_hi: float
    n: int


class DiurnalResponse(BaseModel):
    metric: str
    days_observed: int
    sufficient: bool  # >= 3 distinct days before a diurnal claim is defensible
    cells: list[DiurnalCell]


class GeoPoint(BaseModel):
    lat: float
    lon: float
    label: str
    kind: str  # "you" | "pop"
    out_of_country: bool


class GeoArc(BaseModel):
    from_lat: float
    from_lon: float
    to_lat: float
    to_lon: float
    out_of_country: bool


class GeoResponse(BaseModel):
    points: list[GeoPoint]
    arcs: list[GeoArc]


class DnsCompareRow(BaseModel):
    resolver: str
    n: int
    median_ms: float | None
    p95_ms: float | None
    jitter_ms: float | None  # inter-quartile range
    fail_pct: float


class Status(BaseModel):
    online: bool
    current_rtt: float | None
    current_loss: float | None
    wifi_signal_dbm: float | None
    wifi_bitrate: float | None
    wifi_ssid: str | None
    public_ipv4: str | None
    public_ipv6: str | None
    outages_in_range: int
    latest_download_mbps: float | None
    latest_upload_mbps: float | None
    latest_grade: str | None
    latest_mos: float | None
    interface: str

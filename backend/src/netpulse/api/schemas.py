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

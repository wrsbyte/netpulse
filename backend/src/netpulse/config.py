"""Typed configuration.

Two layers:
* :class:`Settings` — process/runtime settings from env (``NETPULSE_*``) with sane defaults.
* :class:`NetpulseConfig` — the monitoring plan (targets, intervals, alerts) from ``config.toml``.

Both are Pydantic models so everything downstream is typed and validated at load time.
"""

from __future__ import annotations

import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Runtime settings (env-overridable, prefix ``NETPULSE_``)."""

    model_config = SettingsConfigDict(env_prefix="NETPULSE_", env_file=".env", extra="ignore")

    db_path: Path = BACKEND_DIR / "data" / "netpulse.db"
    config_path: Path = BACKEND_DIR / "config.toml"
    host: str = "127.0.0.1"
    port: int = 8477
    log_level: str = "INFO"
    # Absolute path to the built frontend (dist). Served by the API when present.
    frontend_dist: Path = BACKEND_DIR.parent / "frontend" / "dist"


# --- monitoring plan (config.toml) -----------------------------------------

TargetKind = Literal["lan", "internet", "site", "work"]


class Target(BaseModel):
    label: str
    host: str
    kind: TargetKind


class Intervals(BaseModel):
    ping: int = 3
    tcp_connect: int = 15
    wifi: int = 5
    wifi_events: int = 60
    network: int = 15
    throughput: int = 3
    dns: int = 20
    flows: int = 30
    flow_quality: int = 30
    traceroute: int = 300
    wifi_scan: int = 900
    hop_geo: int = 900
    public_ip: int = 300
    anycast: int = 300
    regional: int = 86400
    rollup: int = 300


class Active(BaseModel):
    enabled: bool = True
    interval: int = 900
    bufferbloat: bool = True
    speedtest: bool = True


class Retention(BaseModel):
    raw_hours: int = 48
    agg5m_days: int = 14
    agg1h_days: int = 400


class DnsConfig(BaseModel):
    domains: list[str]
    resolvers: list[str]


class NetpulseConfig(BaseModel):
    interface: str = ""  # empty -> auto-detect default route
    targets: list[Target]
    intervals: Intervals = Intervals()
    active: Active = Active()
    retention: Retention = Retention()
    dns: DnsConfig


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_config() -> NetpulseConfig:
    raw = tomllib.loads(get_settings().config_path.read_text())
    return NetpulseConfig.model_validate(raw)

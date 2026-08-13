"""Declarative base + a shared epoch-seconds timestamp column."""

from __future__ import annotations

from sqlalchemy import Float
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def ts_column() -> Mapped[float]:
    """Sample time as epoch seconds (UTC). Indexed — every query is a time range."""
    return mapped_column(Float, index=True)

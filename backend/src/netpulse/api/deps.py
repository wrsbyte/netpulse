"""FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import HTTPException
from sqlalchemy.orm import Session

from netpulse.api import queries
from netpulse.db.session import get_session

# range -> (agg resolution or "raw", window seconds)
RANGES: dict[str, tuple[str, int]] = {
    "6h": ("raw", 6 * 3600),
    "24h": ("5m", 24 * 3600),
    "7d": ("1h", 7 * 86400),
}


def db() -> Iterator[Session]:
    session = get_session()
    try:
        yield session
    finally:
        session.close()


def window_for(range_key: str) -> tuple[str, int]:
    if range_key not in RANGES:
        raise HTTPException(400, f"range must be one of {list(RANGES)}")
    return RANGES[range_key]


def resolve_network(session: Session, network: str) -> int | None:
    """'current' -> the live network, 'all' -> no filter, else a numeric id."""
    if network == "all":
        return None
    if network == "current":
        return queries.current_network_id(session)
    try:
        return int(network)
    except ValueError:
        raise HTTPException(400, "network must be 'current', 'all', or a numeric id") from None

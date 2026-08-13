"""FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy.orm import Session

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

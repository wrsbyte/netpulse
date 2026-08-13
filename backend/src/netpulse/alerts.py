"""Threshold + duration alerting with desktop notifications.

Each :class:`~netpulse.config.Alert` fires when its metric breaches ``op value`` on average
over the last ``for_seconds``. An alert is stateful: opening logs an :class:`Event` (and a
``notify-send`` desktop toast) once; the event is closed when the condition clears. This is
the SmokePing "sustained breach" model, not per-sample flapping.
"""

from __future__ import annotations

import operator
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from netpulse import shell
from netpulse.aggregation import SOURCES
from netpulse.config import Alert
from netpulse.db.models import Event

_OPS: dict[str, Callable[[float, float], bool]] = {
    "==": operator.eq, ">=": operator.ge, "<=": operator.le, ">": operator.gt, "<": operator.lt,
}
_SOURCE_BY_NAME = {s.name: s for s in SOURCES}


def _window_avg(session: Session, metric: str, start: float) -> float | None:
    source = _SOURCE_BY_NAME.get(metric)
    if source is None:
        return None
    model = source.model
    rows = session.scalars(select(model).where(model.ts >= start)).all()  # type: ignore[attr-defined]
    values = [v for r in rows if (v := getattr(r, source.value_attr)) is not None]
    return sum(values) / len(values) if values else None


def _open_alert(session: Session, name: str) -> Event | None:
    return session.scalars(
        select(Event).where(Event.kind == "alert", Event.detail == name, Event.end_ts.is_(None))
    ).first()


async def _notify(title: str, body: str) -> None:
    if shell.have("notify-send"):
        await shell.run("notify-send", "-a", "netpulse", title, body, timeout=4)


async def evaluate(session: Session, alerts: list[Alert], now: float) -> None:
    for alert in alerts:
        avg = _window_avg(session, alert.metric, now - alert.for_seconds)
        breached = avg is not None and _OPS[alert.op](avg, alert.value)
        existing = _open_alert(session, alert.name)

        if breached and existing is None:
            session.add(Event(
                ts=now, end_ts=None, kind="alert", severity="warning",
                detail=alert.name,
            ))
            await _notify("netpulse alert", f"{alert.name}: {alert.metric}={avg:.1f}")
        elif not breached and existing is not None:
            existing.end_ts = now
    session.commit()

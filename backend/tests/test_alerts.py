import time
from pathlib import Path

from sqlalchemy import func, select

from netpulse.alerts import evaluate
from netpulse.config import Alert
from netpulse.db.models import Event, PingRaw
from netpulse.db.session import get_session, init_engine

LOSS_ALERT = Alert(
    name="sustained loss", metric="ping.loss_pct", op=">=", value=20, for_seconds=300
)


async def test_alert_opens_once_and_does_not_duplicate(tmp_path: Path) -> None:
    init_engine(tmp_path / "al.db")
    now = time.time()
    with get_session() as s:
        s.add_all([PingRaw(ts=now - i, target="1.1.1.1", loss_pct=100.0) for i in range(5)])
        s.commit()

    with get_session() as s:
        await evaluate(s, [LOSS_ALERT], now)
        await evaluate(s, [LOSS_ALERT], now)  # still breached — must not open a second event
        opens = s.scalar(
            select(func.count())
            .select_from(Event)
            .where(Event.kind == "alert", Event.end_ts.is_(None))
        )
    assert opens == 1


async def test_alert_closes_when_condition_clears(tmp_path: Path) -> None:
    init_engine(tmp_path / "al2.db")
    now = time.time()
    with get_session() as s:
        s.add_all([PingRaw(ts=now - i, target="1.1.1.1", loss_pct=100.0) for i in range(5)])
        s.commit()
    with get_session() as s:
        await evaluate(s, [LOSS_ALERT], now)

    # New window with healthy data only -> the open alert should close.
    later = now + 600
    with get_session() as s:
        s.add_all([PingRaw(ts=later - i, target="1.1.1.1", loss_pct=0.0) for i in range(5)])
        s.commit()
        await evaluate(s, [LOSS_ALERT], later)
        open_events = s.scalar(
            select(func.count())
            .select_from(Event)
            .where(Event.kind == "alert", Event.end_ts.is_(None))
        )
    assert open_events == 0

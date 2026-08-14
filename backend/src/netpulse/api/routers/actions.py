"""On-demand actions — run a speedtest now (the dashboard button)."""

from __future__ import annotations

import asyncio
import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from netpulse.api.deps import db
from netpulse.api.schemas import ActivePoint
from netpulse.probes import active

router = APIRouter(prefix="/api/actions", tags=["actions"])
Db = Annotated[Session, Depends(db)]

# One speedtest saturates the link; two at once skew each other's numbers. Serialize + reject the
# second so a double-click (or a click during the hourly cron run) can't run concurrent tests.
_speedtest_lock = asyncio.Lock()


@router.post("/speedtest", response_model=ActivePoint)
async def run_speedtest(session: Db) -> ActivePoint:
    if _speedtest_lock.locked():
        raise HTTPException(409, "a speedtest is already running")
    async with _speedtest_lock:
        row = await active.sample(time.time())
    if row is None:
        raise HTTPException(503, "speedtest unavailable (tool missing or test failed)")
    session.add(row)
    session.commit()
    return ActivePoint(
        ts=row.ts, download_mbps=row.download_mbps, upload_mbps=row.upload_mbps,
        idle_latency=row.idle_latency, bufferbloat_ms=row.bufferbloat_ms,
        grade=row.grade, mos=row.mos,
    )

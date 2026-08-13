"""On-demand actions — run a speedtest now (the dashboard button)."""

from __future__ import annotations

import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from netpulse.api.deps import db
from netpulse.api.schemas import ActivePoint
from netpulse.probes import active

router = APIRouter(prefix="/api/actions", tags=["actions"])
Db = Annotated[Session, Depends(db)]


@router.post("/speedtest", response_model=ActivePoint)
async def run_speedtest(session: Db) -> ActivePoint:
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

"""Safe subprocess helper for probes.

All probes shell out to system tools (``ping``, ``iw``, ``dig`` …). This wraps
``asyncio.create_subprocess_exec`` with a hard timeout and never raises on a non-zero
exit — probes decide what a failure means. No shell is spawned (arg list only), so there
is no injection surface.
"""

from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Result:
    ok: bool  # process ran and exited 0
    code: int | None
    stdout: str
    stderr: str
    timed_out: bool


async def run(*args: str, timeout: float = 10.0) -> Result:  # noqa: ASYNC109 — probe-facing API
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return Result(ok=False, code=None, stdout="", stderr="not found", timed_out=False)

    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return Result(ok=False, code=None, stdout="", stderr="timeout", timed_out=True)

    return Result(
        ok=proc.returncode == 0,
        code=proc.returncode,
        stdout=out.decode(errors="replace"),
        stderr=err.decode(errors="replace"),
        timed_out=False,
    )


def have(tool: str) -> bool:
    """Whether a CLI tool is on PATH (probes degrade gracefully when it isn't)."""
    return shutil.which(tool) is not None

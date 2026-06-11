"""Async sampler for pulse_off_observe.

sample_until reads VOUT/IOUT at a target cadence over a duration window.
Time origin (t_ms = 0) is the moment of the first sample.

Cadence floor: the documented honest minimum sample_interval_ms is 50ms.
Faster requests are clamped to 50ms; a warning surfaces from the caller
(tool_pulse_off_observe), not this layer.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from psu_mcp.session import AsyncProtocolHandle


_MIN_INTERVAL_MS = 50


@dataclass(frozen=True)
class Sample:
    t_ms: int
    vout_mv: int
    iout_ma: int


async def sample_until(
    handle: AsyncProtocolHandle,
    duration_ms: int,
    interval_ms: int,
) -> list[Sample]:
    """Sample VOUT and IOUT at `interval_ms` until `duration_ms` elapses.

    Returns at least one sample (t_ms = 0). Honest interval floor is
    _MIN_INTERVAL_MS -- caller is responsible for warning the agent if a
    smaller value was requested.
    """
    effective_interval = max(interval_ms, _MIN_INTERVAL_MS)
    samples: list[Sample] = []
    start = time.monotonic()
    next_due_s = 0.0

    while True:
        elapsed_s = time.monotonic() - start
        elapsed_ms = int(elapsed_s * 1000)
        vout = await handle.read_vout_mv_async()
        iout = await handle.read_iout_ma_async()
        samples.append(Sample(t_ms=elapsed_ms, vout_mv=vout, iout_ma=iout))

        if elapsed_ms >= duration_ms:
            break

        next_due_s += effective_interval / 1000.0
        sleep_s = next_due_s - (time.monotonic() - start)
        if sleep_s > 0:
            await asyncio.sleep(sleep_s)

    return samples

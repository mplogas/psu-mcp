"""Async wrappers around the sync ProtocolHandle.

psu_session is the per-call context manager: opens serial, yields an
AsyncProtocolHandle, closes serial on exit. Used by every tool that
touches the PSU.

For probing tools (yank_restore, pulse_off_observe), the same session
context manager is used -- the timed cycle happens inside one `async with`
block, so the connection lives for the duration of the cycle without
the open/close overhead per protocol call.

Sync protocol calls are wrapped via asyncio.to_thread so the event loop
is not blocked on pyserial reads/writes.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

import serial as pyserial  # type: ignore[import-untyped]

from psu_mcp.protocol import ProtocolHandle, SerialLike
from psu_mcp.vendors import VendorStrategy


def _open_serial(port: str, vendor: VendorStrategy) -> SerialLike:
    """Open the underlying serial port. Stubbed in tests."""
    return pyserial.Serial(
        port=port,
        baudrate=vendor.baud,
        bytesize=8,
        parity="N",
        stopbits=1,
        timeout=vendor.serial_timeout_s,
    )


class AsyncProtocolHandle:
    """Wraps a sync ProtocolHandle with asyncio.to_thread for async tools."""

    def __init__(self, sync_handle: ProtocolHandle) -> None:
        self._sync = sync_handle

    async def set_voltage_v_async(self, volts: float) -> None:
        await asyncio.to_thread(self._sync.set_voltage_v, volts)

    async def set_current_a_async(self, amps: float) -> None:
        await asyncio.to_thread(self._sync.set_current_a, amps)

    async def output_on_async(self) -> None:
        await asyncio.to_thread(self._sync.output_on)

    async def output_off_async(self) -> None:
        await asyncio.to_thread(self._sync.output_off)

    async def recall_profile_async(self, slot: int) -> None:
        await asyncio.to_thread(self._sync.recall_profile, slot)

    async def read_vset_mv_async(self) -> int:
        return await asyncio.to_thread(self._sync.read_vset_mv)

    async def read_iset_ma_async(self) -> int:
        return await asyncio.to_thread(self._sync.read_iset_ma)

    async def read_vout_mv_async(self) -> int:
        return await asyncio.to_thread(self._sync.read_vout_mv)

    async def read_iout_ma_async(self) -> int:
        return await asyncio.to_thread(self._sync.read_iout_ma)

    async def read_output_on_async(self) -> bool:
        return await asyncio.to_thread(self._sync.read_output_on)

    # Sync access for tight cycles that need to bypass asyncio.to_thread
    # overhead. Use only when timing is critical (yank cycle internals).
    @property
    def sync(self) -> ProtocolHandle:
        return self._sync

    # Direct sync passthroughs for tight cycle internals (proxy each
    # write-only command to the sync handle so callers don't have to
    # reach through .sync explicitly).
    def output_on(self) -> None:
        self._sync.output_on()

    def output_off(self) -> None:
        self._sync.output_off()


@asynccontextmanager
async def psu_session(
    port: str, vendor: VendorStrategy
) -> AsyncIterator[AsyncProtocolHandle]:
    """Open a PSU session, yield an AsyncProtocolHandle, close on exit."""
    serial = _open_serial(port, vendor)
    handle = AsyncProtocolHandle(ProtocolHandle(serial, vendor))
    try:
        yield handle
    finally:
        await asyncio.to_thread(serial.close)

"""Sync pyserial owner. The ONLY module that imports pyserial.

ProtocolHandle wraps a pyserial.Serial-like object and exposes the
Korad/KA3005P command set as typed methods. All values are in milli-units
(mV, mA) at this layer so callers don't deal with floats.

Wire-protocol notes (Korad KA3005P firmware family):
  - 9600 8N1, no flow control
  - No command terminator (commands are content-defined sequences)
  - No response terminator on reads (responses are fixed-format strings or
    single bytes per command)
  - Firmware needs ~50ms settle after a write before responses are stable
  - Write-only commands (OUT1, VSET1:X.XX) need ~30ms settle before the
    next command lands cleanly

Sync because pyserial is sync. session.py wraps these calls in
asyncio.to_thread for the async tool layer.
"""

from __future__ import annotations

import time
from typing import Protocol

from psu_mcp.vendors import VendorStrategy


class SerialLike(Protocol):
    def write(self, data: bytes) -> int: ...
    def read(self, n: int = 1) -> bytes: ...
    def reset_input_buffer(self) -> None: ...
    @property
    def in_waiting(self) -> int: ...
    def close(self) -> None: ...


class ProtocolError(RuntimeError):
    """Raised on wire-protocol failures: empty response, unparseable, etc."""


_READ_BUFFER_BYTES = 64
_STATUS_OUTPUT_ON_BIT = 0x40  # bit 6


class ProtocolHandle:
    def __init__(self, serial: SerialLike, vendor: VendorStrategy) -> None:
        self._serial = serial
        self._vendor = vendor

    # Write-only commands ----------------------------------------------------

    def set_voltage_v(self, volts: float) -> None:
        cmd = self._vendor.cmd_set_voltage.format(v=volts).encode("ascii")
        self._command(cmd)

    def set_current_a(self, amps: float) -> None:
        cmd = self._vendor.cmd_set_current.format(a=amps).encode("ascii")
        self._command(cmd)

    def output_on(self) -> None:
        self._command(self._vendor.cmd_output_on.encode("ascii"))

    def output_off(self) -> None:
        self._command(self._vendor.cmd_output_off.encode("ascii"))

    def recall_profile(self, slot: int) -> None:
        if slot < 1 or slot > self._vendor.profile_count:
            raise ValueError(
                f"slot {slot} out of range 1..{self._vendor.profile_count}"
            )
        cmd = self._vendor.cmd_recall_profile.format(slot=slot).encode("ascii")
        self._command(cmd)

    # Query commands ---------------------------------------------------------

    def read_vset_mv(self) -> int:
        raw = self._query(self._vendor.cmd_read_vset.encode("ascii"))
        return self._parse_fixed_to_milli(raw, self._vendor.cmd_read_vset)

    def read_iset_ma(self) -> int:
        raw = self._query(self._vendor.cmd_read_iset.encode("ascii"))
        return self._parse_fixed_to_milli(raw, self._vendor.cmd_read_iset)

    def read_vout_mv(self) -> int:
        raw = self._query(self._vendor.cmd_read_vout.encode("ascii"))
        return self._parse_fixed_to_milli(raw, self._vendor.cmd_read_vout)

    def read_iout_ma(self) -> int:
        raw = self._query(self._vendor.cmd_read_iout.encode("ascii"))
        return self._parse_fixed_to_milli(raw, self._vendor.cmd_read_iout)

    def read_status_byte(self) -> int:
        raw = self._query(self._vendor.cmd_read_status.encode("ascii"))
        if not raw:
            raise ProtocolError("no response to STATUS?")
        return raw[0]

    def read_output_on(self) -> bool:
        return bool(self.read_status_byte() & _STATUS_OUTPUT_ON_BIT)

    # Internals --------------------------------------------------------------

    def _command(self, payload: bytes) -> None:
        self._serial.write(payload)
        time.sleep(self._vendor.write_settle_s)

    def _query(self, payload: bytes) -> bytes:
        # No reset_input_buffer() before write. Korad firmware is strictly
        # request/response with no unsolicited bytes, so there is no stale
        # data to flush. If a SCPI vendor (Rigol, Siglent) that pushes
        # status messages is added later, flush here -- or better, in
        # session.py on open.
        self._serial.write(payload)
        time.sleep(self._vendor.read_settle_s)
        return self._serial.read(_READ_BUFFER_BYTES)

    @staticmethod
    def _parse_fixed_to_milli(raw: bytes, label: str) -> int:
        if not raw:
            raise ProtocolError(f"no response to {label}")
        text = raw.decode("ascii", errors="replace").strip()
        try:
            return int(round(float(text) * 1000))
        except ValueError:
            raise ProtocolError(f"failed to parse {label} response: {text!r}")

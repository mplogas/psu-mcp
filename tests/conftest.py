"""Shared test fixtures: FakeSerial (Phase 2) and FakePSU (Phase 3).

FakeSerial mimics the pyserial.Serial interface used by protocol.py:
  - write(bytes) -> int        appends to _tx_log
  - read(n) -> bytes           pulls up to n bytes from _rx_buffer
  - reset_input_buffer()       clears _rx_buffer
  - in_waiting (property)      bytes available
  - close()                    no-op

Tests queue responses via fake.queue_response(bytes), then call protocol
methods that write commands and read responses.
"""

from __future__ import annotations

import pytest


class FakeSerial:
    def __init__(self) -> None:
        self._tx_log: list[bytes] = []
        self._rx_buffer: bytearray = bytearray()
        self._closed = False

    def write(self, data: bytes) -> int:
        if self._closed:
            raise RuntimeError("write on closed FakeSerial")
        self._tx_log.append(bytes(data))
        return len(data)

    def read(self, n: int = 1) -> bytes:
        if self._closed:
            raise RuntimeError("read on closed FakeSerial")
        take = min(n, len(self._rx_buffer))
        out = bytes(self._rx_buffer[:take])
        del self._rx_buffer[:take]
        return out

    def reset_input_buffer(self) -> None:
        self._rx_buffer.clear()

    @property
    def in_waiting(self) -> int:
        return len(self._rx_buffer)

    def close(self) -> None:
        self._closed = True

    # Test helpers

    def queue_response(self, data: bytes) -> None:
        """Queue bytes to be returned by subsequent read() calls."""
        self._rx_buffer.extend(data)

    @property
    def tx_log(self) -> list[bytes]:
        return list(self._tx_log)

    @property
    def closed(self) -> bool:
        return self._closed


@pytest.fixture
def fake_serial() -> FakeSerial:
    return FakeSerial()


class FakePSU:
    """KA3005P-protocol fake. Implements the SerialLike protocol with
    in-memory state: vset/iset/output_on/profiles.

    Responds to write() bytes immediately; subsequent read() pulls from
    a per-command response queue populated by the write handler.

    Used by tools tests and the telemetry sampler test to verify
    end-to-end behavior without a real PSU.
    """

    _STATUS_OUTPUT_ON_BIT = 0x40

    def __init__(
        self,
        vset_mv: int = 3300,
        iset_ma: int = 1000,
        output_on: bool = False,
        profiles: dict[int, int] | None = None,
    ) -> None:
        self.vset_mv = vset_mv
        self.iset_ma = iset_ma
        self.output_on = output_on
        # Default: M1..M5 all set to 3300 mV. Tests override.
        self.profiles = profiles or {i: 3300 for i in range(1, 6)}
        # vout/iout reflect what would actually appear on the output:
        # vset/iset when on, 0/0 when off. Tests can override mid-flow.
        self._vout_override: int | None = None
        self._iout_override: int | None = None
        self._rx_buffer: bytearray = bytearray()
        self._tx_log: list[bytes] = []
        self._closed = False

    # SerialLike interface ---------------------------------------------------

    def write(self, data: bytes) -> int:
        if self._closed:
            raise RuntimeError("write on closed FakePSU")
        cmd = data.decode("ascii", errors="replace")
        self._tx_log.append(bytes(data))
        self._handle_command(cmd)
        return len(data)

    def read(self, n: int = 1) -> bytes:
        take = min(n, len(self._rx_buffer))
        out = bytes(self._rx_buffer[:take])
        del self._rx_buffer[:take]
        return out

    def reset_input_buffer(self) -> None:
        self._rx_buffer.clear()

    @property
    def in_waiting(self) -> int:
        return len(self._rx_buffer)

    def close(self) -> None:
        self._closed = True

    # Test helpers -----------------------------------------------------------

    @property
    def tx_log(self) -> list[bytes]:
        return list(self._tx_log)

    @property
    def closed(self) -> bool:
        return self._closed

    def force_vout_mv(self, mv: int | None) -> None:
        """Override the vout reading (None to clear and use vset when on)."""
        self._vout_override = mv

    def force_iout_ma(self, ma: int | None) -> None:
        self._iout_override = ma

    # Command dispatch -------------------------------------------------------

    def _handle_command(self, cmd: str) -> None:
        if cmd.startswith("VSET1:"):
            self.vset_mv = int(round(float(cmd[len("VSET1:"):]) * 1000))
        elif cmd.startswith("ISET1:"):
            self.iset_ma = int(round(float(cmd[len("ISET1:"):]) * 1000))
        elif cmd == "OUT1":
            self.output_on = True
        elif cmd == "OUT0":
            self.output_on = False
        elif cmd.startswith("RCL"):
            slot = int(cmd[3:])
            self.vset_mv = self.profiles.get(slot, self.vset_mv)
        elif cmd == "VSET1?":
            self._respond_volts(self.vset_mv)
        elif cmd == "ISET1?":
            self._respond_amps(self.iset_ma)
        elif cmd == "VOUT1?":
            v = self._vout_override if self._vout_override is not None else (
                self.vset_mv if self.output_on else 0
            )
            self._respond_volts(v)
        elif cmd == "IOUT1?":
            i = self._iout_override if self._iout_override is not None else (
                self.iset_ma if self.output_on else 0
            )
            self._respond_amps(i)
        elif cmd == "STATUS?":
            byte = self._STATUS_OUTPUT_ON_BIT if self.output_on else 0x00
            self._rx_buffer.append(byte)
        # SAV not handled -- spec forbids exposure; if MCP sends it, fail loud

    def _respond_volts(self, mv: int) -> None:
        self._rx_buffer.extend(f"{mv / 1000:.2f}".encode("ascii"))

    def _respond_amps(self, ma: int) -> None:
        self._rx_buffer.extend(f"{ma / 1000:.3f}".encode("ascii"))


@pytest.fixture
def fake_psu() -> FakePSU:
    return FakePSU()

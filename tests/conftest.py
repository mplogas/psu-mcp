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

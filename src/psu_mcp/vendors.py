# src/psu_mcp/vendors.py
"""Per-vendor strategy registry.

A VendorStrategy bundles everything that varies between PSU vendors:
  - serial settings (baud, timeout)
  - command templates for the wire protocol
  - response parsing rules (terminator, decimals, formats)
  - profile slot count (M1-M5 for Korad, varies for others)

MVP registers Korad KA3005P. The RND 320-KA3005P uses the same wire
protocol and reuses the same strategy. Other Korad clones, Rigol/Siglent
SCPI units, and AVR open-source designs are added when hardware is on
the bench to validate the wire format.

The protocol has no command terminator and no response terminator on
KA3005P firmware -- commands and responses are content-defined sequences.
protocol.py uses brief settle sleeps + read-available-bytes to handle this.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


def _identity_parser(data: bytes) -> str:
    return data.decode("ascii", errors="replace").strip()


@dataclass(frozen=True)
class VendorStrategy:
    name: str
    baud: int
    serial_timeout_s: float
    read_settle_s: float    # post-write delay before reading response
    write_settle_s: float   # post-write delay for no-response commands
    cmd_set_voltage: str
    cmd_set_current: str
    cmd_output_on: str
    cmd_output_off: str
    cmd_recall_profile: str
    cmd_read_vset: str
    cmd_read_iset: str
    cmd_read_vout: str
    cmd_read_iout: str
    cmd_read_status: str
    response_terminator: bytes
    response_parser: Callable[[bytes], str]
    voltage_decimals: int
    current_decimals: int
    profile_count: int


KORAD_KA3005P = VendorStrategy(
    name="korad_ka3005p",
    baud=9600,
    serial_timeout_s=0.1,
    read_settle_s=0.05,
    write_settle_s=0.03,
    cmd_set_voltage="VSET1:{v:.2f}",
    cmd_set_current="ISET1:{a:.3f}",
    cmd_output_on="OUT1",
    cmd_output_off="OUT0",
    cmd_recall_profile="RCL{slot}",
    cmd_read_vset="VSET1?",
    cmd_read_iset="ISET1?",
    cmd_read_vout="VOUT1?",
    cmd_read_iout="IOUT1?",
    cmd_read_status="STATUS?",
    response_terminator=b"",
    response_parser=_identity_parser,
    voltage_decimals=2,
    current_decimals=3,
    profile_count=5,
)


_REGISTRY: dict[str, VendorStrategy] = {
    KORAD_KA3005P.name: KORAD_KA3005P,
}


def get_vendor(name: str) -> VendorStrategy:
    v = _REGISTRY.get(name.lower())
    if v is None:
        raise KeyError(
            f"Unknown vendor: {name}. Supported: {sorted(_REGISTRY)}"
        )
    return v


def list_vendors() -> list[VendorStrategy]:
    return list(_REGISTRY.values())

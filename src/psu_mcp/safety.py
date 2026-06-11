"""Three-tier safety model + configured bounds for psu-mcp.

Tiers:
  read-only       -- full autonomy, no PSU state change
  allowed-write   -- autonomous but logged; output-affecting tools live here
  approval-write  -- blocks until human supplies _confirmed token

Bounds are configured at MCP startup via .mcp.json -> PSU_CONFIG_PATH ->
config.max_voltage_mv / max_current_ma. Tools consult Bounds at entry; the
voltage check is duplicated even with _confirmed because the disaster case
is firing 5V at a 3.3V chip when M1 happened to default to 5V.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SafetyTier(Enum):
    READ_ONLY = "read-only"
    ALLOWED_WRITE = "allowed-write"
    APPROVAL_WRITE = "approval-write"


_TOOL_TIERS: dict[str, SafetyTier] = {
    "connect": SafetyTier.READ_ONLY,
    "list_profiles": SafetyTier.READ_ONLY,
    "get_status": SafetyTier.READ_ONLY,
    "recall_profile": SafetyTier.ALLOWED_WRITE,
    "set_current_limit": SafetyTier.ALLOWED_WRITE,
    "output_on": SafetyTier.ALLOWED_WRITE,
    "output_off": SafetyTier.ALLOWED_WRITE,
    "yank_restore": SafetyTier.ALLOWED_WRITE,
    "pulse_off_observe": SafetyTier.ALLOWED_WRITE,
    "set_voltage": SafetyTier.APPROVAL_WRITE,
}


def classify_tool(tool_name: str) -> SafetyTier:
    tier = _TOOL_TIERS.get(tool_name)
    if tier is None:
        raise ValueError(f"Unknown tool: {tool_name}")
    return tier


@dataclass(frozen=True)
class Bounds:
    max_voltage_mv: int
    max_current_ma: int


class BoundsError(ValueError):
    """Raised when a value exceeds the configured bound."""


def check_voltage_bound(voltage_mv: int, bounds: Bounds) -> int:
    if voltage_mv > bounds.max_voltage_mv:
        raise BoundsError(
            f"voltage {voltage_mv} mV exceeds configured max {bounds.max_voltage_mv} mV"
        )
    return voltage_mv


def check_current_bound(current_ma: int, bounds: Bounds) -> int:
    if current_ma > bounds.max_current_ma:
        raise BoundsError(
            f"current {current_ma} mA exceeds configured max {bounds.max_current_ma} mA"
        )
    return current_ma

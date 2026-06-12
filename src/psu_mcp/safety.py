"""Three-tier safety model for psu-mcp.

Tiers:
  read-only       -- full autonomy, no PSU state change
  allowed-write   -- autonomous but logged; output-affecting tools live here
  approval-write  -- reserved tier; no tools currently in this tier

Voltage and current authority is hardware, not software. The operator
pre-loads M1-M5 at the bench; the agent recalls slots by index. There is
no MCP-side voltage setter -- profile-as-protection is the contract.
Output-affecting tools verify that the live VSET matches one of the
operator-declared profile mv values before enabling output. A stray
VSET (panel knob, post-power-cycle default, prior session) does not
satisfy the check; the agent must call recall_profile first.
"""

from __future__ import annotations

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
    "output_on": SafetyTier.ALLOWED_WRITE,
    "output_off": SafetyTier.ALLOWED_WRITE,
    "yank_restore": SafetyTier.ALLOWED_WRITE,
    "pulse_off_observe": SafetyTier.ALLOWED_WRITE,
}


def classify_tool(tool_name: str) -> SafetyTier:
    tier = _TOOL_TIERS.get(tool_name)
    if tier is None:
        raise ValueError(f"Unknown tool: {tool_name}")
    return tier


def vset_matches_declared_profile(vset_mv: int, declared_mvs: set[int]) -> bool:
    """True if vset_mv equals any operator-declared profile mv."""
    return vset_mv in declared_mvs

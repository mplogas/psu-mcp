"""Operator-declared profile config + schema validation.

The config file lives at PSU_CONFIG_PATH (env var) and declares:
  - port, vendor (single PSU per MCP instance)
  - profiles: slot -> {mv, label} mapping for M1-M5

Profiles ARE the safety boundary. Each declared mv is the operator's
deliberate physical loading of that PSU memory slot. There is no
separate max-voltage / max-current config -- the set of declared
profile mv values is what the agent is allowed to fire at a target.

Profiles are required and must be non-empty. A psu-mcp with no
profiles cannot enable output (output_on refuses unless VSET equals
one of the declared mv values). That refusal is the contract.

Profiles may be sparse (declare slots 1 and 3, skip 2). connect verifies
declared slots against live VSET; undeclared slots are not recalled.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


class ConfigError(ValueError):
    """Raised when the config file is missing, malformed, or fails schema."""


@dataclass(frozen=True)
class Profile:
    slot: int
    mv: int
    label: str


@dataclass(frozen=True)
class PSUConfig:
    port: str
    vendor: str
    profiles: dict[int, Profile] = field(default_factory=dict)

    def declared_mvs(self) -> set[int]:
        """Set of all declared profile mv values. Used by output guards."""
        return {p.mv for p in self.profiles.values()}


_REQUIRED_TOP = ("port", "vendor", "profiles")


def load_config(path: Path) -> PSUConfig:
    if not path.exists():
        raise ConfigError(f"config file not found: {path}")
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise ConfigError(f"failed to parse config {path}: {e}")

    for key in _REQUIRED_TOP:
        if key not in raw:
            raise ConfigError(f"config missing required key: {key}")

    profiles: dict[int, Profile] = {}
    raw_profiles = raw["profiles"]
    if not isinstance(raw_profiles, dict):
        raise ConfigError("profiles must be a JSON object")
    if not raw_profiles:
        raise ConfigError(
            "profiles must declare at least one slot -- psu-mcp cannot enable "
            "output without a declared profile"
        )

    for slot_key, body in raw_profiles.items():
        try:
            slot = int(slot_key)
        except (TypeError, ValueError):
            raise ConfigError(f"profile slot must be int-like, got: {slot_key!r}")
        if not isinstance(body, dict):
            raise ConfigError(f"profile slot {slot}: body must be an object")
        if "mv" not in body:
            raise ConfigError(f"profile slot {slot}: missing mv")
        if "label" not in body:
            raise ConfigError(f"profile slot {slot}: missing label")
        profiles[slot] = Profile(
            slot=slot,
            mv=int(body["mv"]),
            label=str(body["label"]),
        )

    return PSUConfig(
        port=str(raw["port"]),
        vendor=str(raw["vendor"]),
        profiles=profiles,
    )

"""Operator-declared profile config + schema validation.

The config file lives at PSU_CONFIG_PATH (env var) and declares:
  - port, vendor (single PSU per MCP instance)
  - max_voltage_mv, max_current_ma (engagement-level safety bounds)
  - profiles: slot -> {mv, label} mapping for M1-M5

Profiles are optional and may be sparse (declare slots 1 and 3, skip 2).
connect verifies declared slots against live VSET; undeclared slots are
ignored entirely (operator's call -- maybe they're playground slots).
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
    max_voltage_mv: int
    max_current_ma: int
    profiles: dict[int, Profile] = field(default_factory=dict)


_REQUIRED_TOP = ("port", "vendor", "max_voltage_mv", "max_current_ma")


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
    raw_profiles = raw.get("profiles", {})
    if not isinstance(raw_profiles, dict):
        raise ConfigError("profiles must be a JSON object")

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
        max_voltage_mv=int(raw["max_voltage_mv"]),
        max_current_ma=int(raw["max_current_ma"]),
        profiles=profiles,
    )

"""Async tool implementations.

Each tool function:
  - takes a PSUConfig (and tool-specific args)
  - opens a session via psu_session (per-call default)
  - runs the protocol steps
  - returns a dict matching the spec contract

Tools never raise to the MCP layer. Failures return a dict with
{"ok": False, "error": <category>, "message": <human>, "details": <dict>}.
"""

from __future__ import annotations

from psu_mcp.profiles import PSUConfig
from psu_mcp.safety import Bounds, BoundsError, check_voltage_bound
from psu_mcp.session import psu_session
from psu_mcp.vendors import get_vendor


def _bounds_from_config(config: PSUConfig) -> Bounds:
    return Bounds(
        max_voltage_mv=config.max_voltage_mv,
        max_current_ma=config.max_current_ma,
    )


def _error(category: str, message: str, **details) -> dict:
    return {
        "ok": False,
        "error": category,
        "message": message,
        "details": details,
    }


async def tool_connect(config: PSUConfig) -> dict:
    vendor = get_vendor(config.vendor)
    warnings: list[str] = []
    try:
        async with psu_session(config.port, vendor) as handle:
            vset = await handle.read_vset_mv_async()
            iset = await handle.read_iset_ma_async()
            output_on = await handle.read_output_on_async()

            if vset > config.max_voltage_mv:
                warnings.append(
                    f"VSET {vset} mV exceeds configured max {config.max_voltage_mv} mV"
                )
            if iset > config.max_current_ma:
                warnings.append(
                    f"ISET {iset} mA exceeds configured max {config.max_current_ma} mA"
                )

            if output_on:
                warnings.append(
                    "profile_verification_skipped: output is on; recalling slots would "
                    "whipsaw the live voltage. Call output_off then re-run connect."
                )
            else:
                # Verify declared profiles by recalling each one.
                # vset will be left at whatever the last recall loaded;
                # caller can re-set if needed via set_voltage or recall_profile.
                for slot, profile in sorted(config.profiles.items()):
                    await handle.recall_profile_async(slot)
                    actual = await handle.read_vset_mv_async()
                    if actual != profile.mv:
                        warnings.append(
                            f"profile mismatch slot {slot} ({profile.label}): "
                            f"declared {profile.mv} mV, actual {actual} mV"
                        )

            return {
                "ok": True,
                "vendor": vendor.name,
                "port": config.port,
                "vset_mv": vset,
                "iset_ma": iset,
                "output_on": output_on,
                "warnings": warnings,
            }
    except Exception as e:
        return _error("connect_failed", str(e))


async def tool_list_profiles(config: PSUConfig) -> dict:
    return {
        "ok": True,
        "profiles": {
            slot: {"mv": p.mv, "label": p.label}
            for slot, p in config.profiles.items()
        },
    }


async def tool_get_status(config: PSUConfig) -> dict:
    vendor = get_vendor(config.vendor)
    warnings: list[str] = []
    try:
        async with psu_session(config.port, vendor) as handle:
            vset = await handle.read_vset_mv_async()
            iset = await handle.read_iset_ma_async()
            vout = await handle.read_vout_mv_async()
            iout = await handle.read_iout_ma_async()
            output_on = await handle.read_output_on_async()

            if vset > config.max_voltage_mv:
                warnings.append(
                    f"VSET {vset} mV exceeds configured max {config.max_voltage_mv} mV"
                )
            if iset > config.max_current_ma:
                warnings.append(
                    f"ISET {iset} mA exceeds configured max {config.max_current_ma} mA"
                )

            return {
                "ok": True,
                "vendor": vendor.name,
                "vset_mv": vset,
                "iset_ma": iset,
                "vout_mv": vout,
                "iout_ma": iout,
                "output_on": output_on,
                "bounds": {
                    "max_voltage_mv": config.max_voltage_mv,
                    "max_current_ma": config.max_current_ma,
                },
                "warnings": warnings,
            }
    except Exception as e:
        return _error("status_failed", str(e))


_SET_VOLTAGE_CONFIRM_TOKEN = "I understand the voltage risk"


async def tool_set_voltage(
    config: PSUConfig,
    voltage_mv: int,
    _confirmed: str | None = None,
) -> dict:
    if voltage_mv < 0:
        return _error("invalid_argument", "voltage_mv must be non-negative")
    if _confirmed != _SET_VOLTAGE_CONFIRM_TOKEN:
        return _error(
            "confirmation_required",
            "set_voltage requires _confirmed token",
            expected_token=_SET_VOLTAGE_CONFIRM_TOKEN,
        )
    bounds = _bounds_from_config(config)
    try:
        check_voltage_bound(voltage_mv, bounds)
    except BoundsError as e:
        return _error("bounds_exceeded", str(e))

    vendor = get_vendor(config.vendor)
    try:
        async with psu_session(config.port, vendor) as handle:
            await handle.set_voltage_v_async(voltage_mv / 1000.0)
            actual = await handle.read_vset_mv_async()
            return {"ok": True, "vset_mv": actual}
    except Exception as e:
        return _error("set_voltage_failed", str(e))

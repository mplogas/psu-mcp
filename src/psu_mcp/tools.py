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

import asyncio
import time

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


from psu_mcp.safety import check_current_bound


async def tool_set_current_limit(config: PSUConfig, current_ma: int) -> dict:
    if current_ma < 0:
        return _error("invalid_argument", "current_ma must be non-negative")
    bounds = _bounds_from_config(config)
    try:
        check_current_bound(current_ma, bounds)
    except BoundsError as e:
        return _error("bounds_exceeded", str(e))

    vendor = get_vendor(config.vendor)
    try:
        async with psu_session(config.port, vendor) as handle:
            await handle.set_current_a_async(current_ma / 1000.0)
            actual = await handle.read_iset_ma_async()
            return {"ok": True, "iset_ma": actual}
    except Exception as e:
        return _error("set_current_failed", str(e))


async def tool_output_on(config: PSUConfig) -> dict:
    vendor = get_vendor(config.vendor)
    bounds = _bounds_from_config(config)
    try:
        async with psu_session(config.port, vendor) as handle:
            vset = await handle.read_vset_mv_async()
            iset = await handle.read_iset_ma_async()
            if vset > bounds.max_voltage_mv or iset > bounds.max_current_ma:
                return _error(
                    "bounds_exceeded_pre_flight",
                    f"refusing output_on: VSET={vset} mV (max {bounds.max_voltage_mv}), "
                    f"ISET={iset} mA (max {bounds.max_current_ma})",
                    vset_mv=vset,
                    iset_ma=iset,
                )
            await handle.output_on_async()
            return {"ok": True, "output_on": True, "vset_mv": vset, "iset_ma": iset}
    except Exception as e:
        return _error("output_on_failed", str(e))


async def tool_output_off(config: PSUConfig) -> dict:
    vendor = get_vendor(config.vendor)
    try:
        async with psu_session(config.port, vendor) as handle:
            await handle.output_off_async()
            return {"ok": True, "output_on": False}
    except Exception as e:
        return _error("output_off_failed", str(e))


async def tool_recall_profile(config: PSUConfig, slot: int) -> dict:
    vendor = get_vendor(config.vendor)
    if slot < 1 or slot > vendor.profile_count:
        return _error(
            "slot_invalid",
            f"slot {slot} out of range 1..{vendor.profile_count}",
        )
    bounds = _bounds_from_config(config)
    try:
        async with psu_session(config.port, vendor) as handle:
            output_was_on = await handle.read_output_on_async()
            await handle.recall_profile_async(slot)
            vset = await handle.read_vset_mv_async()
            iset = await handle.read_iset_ma_async()
            if vset > bounds.max_voltage_mv or iset > bounds.max_current_ma:
                if output_was_on:
                    await handle.output_off_async()
                return _error(
                    "bounds_exceeded_post_recall",
                    f"recall loaded VSET={vset} mV / ISET={iset} mA exceeds bounds; "
                    f"output {'forced off' if output_was_on else 'remains off'}",
                    vset_mv=vset,
                    iset_ma=iset,
                )
            return {
                "ok": True,
                "slot": slot,
                "loaded_vset_mv": vset,
                "loaded_iset_ma": iset,
            }
    except Exception as e:
        return _error("recall_failed", str(e))


async def tool_yank_restore(
    config: PSUConfig,
    off_ms: int,
    on_ms: int = 0,
    repeat: int = 1,
) -> dict:
    if off_ms < 0 or on_ms < 0:
        return _error("invalid_argument", "off_ms and on_ms must be non-negative")
    if repeat < 1:
        return _error("invalid_argument", "repeat must be >= 1")
    if repeat > 1 and on_ms <= 0:
        return _error(
            "sanity_violation",
            "repeat > 1 requires on_ms > 0 (>=50ms recommended) to avoid "
            "racing output_off against the prior output_on with only serial "
            "latency between cycles",
        )

    vendor = get_vendor(config.vendor)
    bounds = _bounds_from_config(config)
    cycles: list[dict] = []
    try:
        async with psu_session(config.port, vendor) as handle:
            # Pre-flight bounds check at tool entry. No further checks
            # during the cycle -- atomicity preserves yank timing.
            vset = await handle.read_vset_mv_async()
            iset = await handle.read_iset_ma_async()
            if vset > bounds.max_voltage_mv or iset > bounds.max_current_ma:
                return _error(
                    "bounds_exceeded_pre_flight",
                    f"refusing cycle: VSET={vset} mV (max {bounds.max_voltage_mv}), "
                    f"ISET={iset} mA (max {bounds.max_current_ma})",
                    vset_mv=vset,
                    iset_ma=iset,
                )

            for _ in range(repeat):
                t0 = time.monotonic()
                await handle.output_off_async()
                await asyncio.sleep(off_ms / 1000.0)
                t1 = time.monotonic()
                await handle.output_on_async()
                if on_ms > 0:
                    await asyncio.sleep(on_ms / 1000.0)
                t2 = time.monotonic()
                cycles.append({
                    "off_ms_actual": int((t1 - t0) * 1000),
                    "on_ms_actual": int((t2 - t1) * 1000),
                })

            return {"ok": True, "cycles": cycles}
    except Exception as e:
        # Best-effort: try to leave the PSU off, since on the way out we
        # may have just disabled it. If reopening fails we accept that.
        try:
            async with psu_session(config.port, vendor) as h2:
                await h2.output_off_async()
        except Exception:
            pass
        return _error(
            "cycle_aborted_serial_drop", str(e), cycles_completed=cycles
        )

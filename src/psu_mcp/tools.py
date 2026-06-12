"""Async tool implementations.

Each tool function:
  - takes a PSUConfig (and tool-specific args)
  - opens a session via psu_session (per-call default)
  - runs the protocol steps
  - returns a dict matching the spec contract

Tools never raise to the MCP layer. Failures return a dict with
{"ok": False, "error": <category>, "message": <human>, "details": <dict>}.

Output safety contract: the agent cannot set voltage or current. It can
only recall a declared profile slot. Output-affecting tools refuse to
enable output unless the live VSET equals one of the operator-declared
profile mv values. A stray VSET (panel knob, post-power-cycle default,
prior session) does not satisfy the check.
"""

from __future__ import annotations

import asyncio
import time

from psu_mcp.engagement import (
    EngagementLoggingError,
    append_log_line,
    now_iso,
    resolve_log_path,
)
from psu_mcp.profiles import PSUConfig
from psu_mcp.safety import vset_matches_declared_profile
from psu_mcp.session import psu_session
from psu_mcp.telemetry import sample_until
from psu_mcp.vendors import get_vendor


_TELEMETRY_INTERVAL_FLOOR_MS = 50


def _log_invocation(
    engagement_name: str | None,
    project_path: str | None,
    tool: str,
    args: dict,
    result: dict,
) -> str | None:
    """Append a JSONL entry to the engagement log if requested.

    Returns a warning string on failure (so the caller can surface it in
    result["warnings"]) or None on success / no-op.
    """
    try:
        log_path = resolve_log_path(engagement_name, project_path)
    except EngagementLoggingError as e:
        return f"engagement_log_skipped: {e}"
    if log_path is None:
        return None
    entry = {
        "timestamp": now_iso(),
        "tool": tool,
        "args": args,
        "result": result,
    }
    try:
        append_log_line(log_path, entry)
    except OSError as e:
        return f"engagement_log_write_failed: {e}"
    return None


def _error(category: str, message: str, **details) -> dict:
    return {
        "ok": False,
        "error": category,
        "message": message,
        "details": details,
    }


def _vset_unrecognized_error(vset: int, config: PSUConfig) -> dict:
    return _error(
        "vset_unrecognized",
        f"VSET {vset} mV does not match any declared profile. "
        "Call recall_profile to load a declared slot before enabling output.",
        vset_mv=vset,
        declared_profiles={s: p.mv for s, p in config.profiles.items()},
    )


async def tool_connect(config: PSUConfig) -> dict:
    vendor = get_vendor(config.vendor)
    warnings: list[str] = []
    try:
        async with psu_session(config.port, vendor) as handle:
            vset = await handle.read_vset_mv_async()
            iset = await handle.read_iset_ma_async()
            output_on = await handle.read_output_on_async()

            if output_on:
                warnings.append(
                    "profile_verification_skipped: output is on; recalling slots "
                    "would whipsaw the live voltage. Call output_off then re-run "
                    "connect."
                )
            else:
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

            declared_mvs = config.declared_mvs()
            if not vset_matches_declared_profile(vset, declared_mvs):
                warnings.append(
                    f"VSET {vset} mV does not match any declared profile "
                    f"({sorted(declared_mvs)} mV). output_on will refuse until "
                    "recall_profile is called."
                )

            return {
                "ok": True,
                "vendor": vendor.name,
                "vset_mv": vset,
                "iset_ma": iset,
                "vout_mv": vout,
                "iout_ma": iout,
                "output_on": output_on,
                "declared_profiles": {
                    s: {"mv": p.mv, "label": p.label}
                    for s, p in config.profiles.items()
                },
                "warnings": warnings,
            }
    except Exception as e:
        return _error("status_failed", str(e))


async def tool_output_on(config: PSUConfig) -> dict:
    vendor = get_vendor(config.vendor)
    declared_mvs = config.declared_mvs()
    try:
        async with psu_session(config.port, vendor) as handle:
            vset = await handle.read_vset_mv_async()
            if not vset_matches_declared_profile(vset, declared_mvs):
                return _vset_unrecognized_error(vset, config)
            await handle.output_on_async()
            return {"ok": True, "output_on": True, "vset_mv": vset}
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
    declared = config.profiles.get(slot)
    if declared is None:
        return _error(
            "slot_not_declared",
            f"slot {slot} is not declared in config; psu-mcp can only recall "
            "operator-declared slots",
            declared_slots=sorted(config.profiles.keys()),
        )
    try:
        async with psu_session(config.port, vendor) as handle:
            output_was_on = await handle.read_output_on_async()
            await handle.recall_profile_async(slot)
            vset = await handle.read_vset_mv_async()
            iset = await handle.read_iset_ma_async()
            if vset != declared.mv:
                if output_was_on:
                    await handle.output_off_async()
                return _error(
                    "profile_mismatch",
                    f"recall slot {slot} loaded VSET={vset} mV, declared "
                    f"{declared.mv} mV. Operator config and bench panel disagree. "
                    f"Output {'forced off' if output_was_on else 'remains off'}.",
                    slot=slot,
                    declared_mv=declared.mv,
                    actual_mv=vset,
                )
            return {
                "ok": True,
                "slot": slot,
                "label": declared.label,
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
    engagement_name: str | None = None,
    project_path: str | None = None,
) -> dict:
    args = {"off_ms": off_ms, "on_ms": on_ms, "repeat": repeat}
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
    declared_mvs = config.declared_mvs()
    cycles: list[dict] = []
    try:
        async with psu_session(config.port, vendor) as handle:
            vset = await handle.read_vset_mv_async()
            if not vset_matches_declared_profile(vset, declared_mvs):
                result = _vset_unrecognized_error(vset, config)
                _maybe_attach_log_warning(
                    result, engagement_name, project_path,
                    "yank_restore", args,
                )
                return result

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

            result = {"ok": True, "cycles": cycles, "warnings": []}
            _maybe_attach_log_warning(
                result, engagement_name, project_path,
                "yank_restore", args,
            )
            return result
    except Exception as e:
        try:
            async with psu_session(config.port, vendor) as h2:
                await h2.output_off_async()
        except Exception:
            pass
        result = _error(
            "cycle_aborted_serial_drop", str(e), cycles_completed=cycles
        )
        _maybe_attach_log_warning(
            result, engagement_name, project_path,
            "yank_restore", args,
        )
        return result


def _maybe_attach_log_warning(
    result: dict,
    engagement_name: str | None,
    project_path: str | None,
    tool: str,
    args: dict,
) -> None:
    """Write the engagement log line for `result`; attach warning on failure."""
    warning = _log_invocation(engagement_name, project_path, tool, args, result)
    if warning:
        result.setdefault("warnings", []).append(warning)


async def tool_pulse_off_observe(
    config: PSUConfig,
    off_ms: int,
    observe_ms: int,
    sample_interval_ms: int = 50,
    engagement_name: str | None = None,
    project_path: str | None = None,
) -> dict:
    args = {
        "off_ms": off_ms,
        "observe_ms": observe_ms,
        "sample_interval_ms": sample_interval_ms,
    }
    if off_ms < 0 or observe_ms < 0 or sample_interval_ms < 0:
        return _error(
            "invalid_argument",
            "off_ms, observe_ms, sample_interval_ms must be non-negative",
        )

    warnings: list[str] = []
    effective_interval = sample_interval_ms
    if 0 < sample_interval_ms < _TELEMETRY_INTERVAL_FLOOR_MS:
        warnings.append(
            f"sample_interval_ms={sample_interval_ms} below honest floor "
            f"{_TELEMETRY_INTERVAL_FLOOR_MS}ms; clamping. Korad serial round-trip "
            f"dominates faster requests."
        )
        effective_interval = _TELEMETRY_INTERVAL_FLOOR_MS

    vendor = get_vendor(config.vendor)
    declared_mvs = config.declared_mvs()
    try:
        async with psu_session(config.port, vendor) as handle:
            vset = await handle.read_vset_mv_async()
            if not vset_matches_declared_profile(vset, declared_mvs):
                result = _vset_unrecognized_error(vset, config)
                _maybe_attach_log_warning(
                    result, engagement_name, project_path,
                    "pulse_off_observe", args,
                )
                return result

            t0 = time.monotonic()
            await handle.output_off_async()
            await asyncio.sleep(off_ms / 1000.0)
            t1 = time.monotonic()
            await handle.output_on_async()
            t_restore = time.monotonic()

            samples = await sample_until(
                handle, duration_ms=observe_ms, interval_ms=effective_interval
            )

            result = {
                "ok": True,
                "cycle": {
                    "off_ms_requested": off_ms,
                    "off_ms_actual": int((t1 - t0) * 1000),
                    "on_at_ms": int((t_restore - t0) * 1000),
                },
                "telemetry": [
                    {"t_ms": s.t_ms, "vout_mv": s.vout_mv, "iout_ma": s.iout_ma}
                    for s in samples
                ],
                "warnings": warnings,
            }
            _maybe_attach_log_warning(
                result, engagement_name, project_path,
                "pulse_off_observe", args,
            )
            return result
    except Exception as e:
        try:
            async with psu_session(config.port, vendor) as h2:
                await h2.output_off_async()
        except Exception:
            pass
        result = _error("cycle_aborted_serial_drop", str(e))
        _maybe_attach_log_warning(
            result, engagement_name, project_path,
            "pulse_off_observe", args,
        )
        return result

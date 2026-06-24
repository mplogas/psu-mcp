"""MCP server: tool definitions and call_tool dispatch.

The server is a thin layer that:
  - declares the 8 tools with input schemas (for the MCP client UI)
  - loads PSUConfig once from the PSU_CONFIG_PATH env var
  - routes calls to the corresponding tools.tool_* function
  - returns the result dict as the MCP tool response

All tool logic lives in tools.py. The server adds no behavior beyond
dispatch. Voltage and current setters are intentionally absent --
profile-as-protection means the operator controls voltage at the bench,
and the agent only recalls declared profile slots.
"""

from __future__ import annotations

import os
from pathlib import Path

import mcp.server.stdio
import mcp.types as types
from mcp.server import Server

from psu_mcp.profiles import PSUConfig, load_config
from psu_mcp.tools import (
    tool_connect,
    tool_get_status,
    tool_list_profiles,
    tool_output_off,
    tool_output_on,
    tool_pulse_off_observe,
    tool_recall_profile,
    tool_yank_restore,
)


# Duration class convention (consistent across pidev-sec tool MCPs):
#   instant    -- <1 s wall clock, foregroundable always
#   fast       -- 1-10 s, foregroundable; backgrounding adds overhead with no benefit
#   slow       -- 10 s-2 min, background-dispatch recommended if the agent has other work
#   very-slow  -- >2 min, background-dispatch effectively required
# Append to every tool description as: [Duration: <class>. <Orchestration note if relevant>.]


TOOL_DEFINITIONS: list[types.Tool] = [
    types.Tool(
        name="connect",
        description=(
            "Probe the PSU on the configured serial port. Returns vendor, "
            "current VSET/ISET, output state, and verifies declared profiles "
            "against live VSET. Skips profile verification if output is on. "
            "[Duration: fast (~1 s for the read + 1 short query per declared profile slot).]"
        ),
        inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
    ),
    types.Tool(
        name="list_profiles",
        description=(
            "Return operator-declared profile slot labels from config. "
            "[Duration: instant (no I/O).]"
        ),
        inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
    ),
    types.Tool(
        name="get_status",
        description=(
            "Return live PSU state: vout/iout/vset/iset/output_on/vendor and "
            "declared profiles. Warns if VSET does not match any declared "
            "profile (output_on will refuse in that case). Useful as a "
            "post-yank bootloader-entry check: read iout_ma to confirm chip "
            "state without touching UART. "
            "[Duration: instant (~0.5 s, 5 serial reads).]"
        ),
        inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
    ),
    types.Tool(
        name="recall_profile",
        description=(
            "Load operator-declared profile slot N into the active VSET/ISET. "
            "Refuses slots not in config. Verifies loaded VSET matches the "
            "declared mv; forces output_off if mismatch and output was on. "
            "[Duration: instant (~0.3 s).]"
        ),
        inputSchema={
            "type": "object",
            "properties": {"slot": {"type": "integer", "minimum": 1, "maximum": 5}},
            "required": ["slot"],
            "additionalProperties": False,
        },
    ),
    types.Tool(
        name="output_on",
        description=(
            "Enable PSU output. Refuses if live VSET does not match any "
            "operator-declared profile (the agent has no way to set voltage; "
            "VSET must arrive via recall_profile). "
            "[Duration: instant (~0.2 s).]"
        ),
        inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
    ),
    types.Tool(
        name="output_off",
        description=(
            "Disable PSU output. Always safe. "
            "[Duration: instant (~0.1 s).]"
        ),
        inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
    ),
    types.Tool(
        name="yank_restore",
        description=(
            "Atomic power cycle: output_off, sleep(off_ms), output_on, sleep(on_ms). "
            "Optional `repeat` for multi-pulse entry patterns; repeat>1 requires "
            "on_ms>0. Pre-flight check at tool entry refuses if live VSET does "
            "not match a declared profile. Optional engagement_name / engagement_path "
            "append a JSONL log line to <engagement>/uart/logs/psu.jsonl. "
            "[Duration: ~(off_ms + on_ms) * repeat + ~60 ms overhead per cycle. "
            "Foreground only -- the timing IS the value. Orchestration: when "
            "paired with a HITL flasher tool (ltchiptool.start_chip_info, etc.), "
            "the flasher must be dispatched in a background subagent FIRST, then "
            "wait ~10 s for it to open the port, then call this from main. See "
            "skills/ltchiptool-probe.md section 3a.]"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "off_ms": {"type": "integer", "minimum": 0},
                "on_ms": {"type": "integer", "minimum": 0, "default": 0},
                "repeat": {"type": "integer", "minimum": 1, "default": 1},
                "engagement_name": {"type": "string"},
                "engagement_path": {"type": "string"},
            },
            "required": ["off_ms"],
            "additionalProperties": False,
        },
    ),
    types.Tool(
        name="pulse_off_observe",
        description=(
            "Atomic: profile check, output_off, sleep(off_ms), output_on, sample "
            "VOUT/IOUT at sample_interval_ms for observe_ms. Returns timeseries "
            "(t_ms relative to restore). Honest sampling floor 50 ms. Optional "
            "engagement_name / engagement_path append a JSONL log line to "
            "<engagement>/uart/logs/psu.jsonl, including the full telemetry array. "
            "[Duration: ~off_ms + observe_ms + ~0.3 s overhead. Foreground recommended. "
            "Same HITL-orchestration note as yank_restore if used to enter bootloader.]"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "off_ms": {"type": "integer", "minimum": 0},
                "observe_ms": {"type": "integer", "minimum": 0},
                "sample_interval_ms": {"type": "integer", "minimum": 0, "default": 50},
                "engagement_name": {"type": "string"},
                "engagement_path": {"type": "string"},
            },
            "required": ["off_ms", "observe_ms"],
            "additionalProperties": False,
        },
    ),
]


def _load_config_from_env() -> PSUConfig:
    path_str = os.environ.get("PSU_CONFIG_PATH")
    if not path_str:
        raise RuntimeError(
            "PSU_CONFIG_PATH env var not set; see README for config schema"
        )
    return load_config(Path(path_str))


async def call_tool(name: str, args: dict) -> dict:
    if name in {"yank_restore", "pulse_off_observe"} and "project_path" in args:
        return {
            "ok": False,
            "error": "renamed_argument",
            "message": (
                "project_path was renamed to engagement_path in v0.3; "
                "pass engagement_path instead."
            ),
            "details": {"argument": "project_path"},
        }
    config = _load_config_from_env()
    if name == "connect":
        return await tool_connect(config)
    if name == "list_profiles":
        return await tool_list_profiles(config)
    if name == "get_status":
        return await tool_get_status(config)
    if name == "recall_profile":
        return await tool_recall_profile(config, slot=int(args["slot"]))
    if name == "output_on":
        return await tool_output_on(config)
    if name == "output_off":
        return await tool_output_off(config)
    if name == "yank_restore":
        return await tool_yank_restore(
            config,
            off_ms=int(args["off_ms"]),
            on_ms=int(args.get("on_ms", 0)),
            repeat=int(args.get("repeat", 1)),
            engagement_name=args.get("engagement_name"),
            engagement_path=args.get("engagement_path"),
        )
    if name == "pulse_off_observe":
        return await tool_pulse_off_observe(
            config,
            off_ms=int(args["off_ms"]),
            observe_ms=int(args["observe_ms"]),
            sample_interval_ms=int(args.get("sample_interval_ms", 50)),
            engagement_name=args.get("engagement_name"),
            engagement_path=args.get("engagement_path"),
        )
    return {
        "ok": False,
        "error": "unknown_tool",
        "message": f"no tool named {name}",
        "details": {"name": name},
    }


async def main() -> None:
    server: Server = Server("psu-mcp")

    @server.list_tools()
    async def _list() -> list[types.Tool]:
        return TOOL_DEFINITIONS

    @server.call_tool()
    async def _call(name: str, arguments: dict) -> list[types.TextContent]:
        import json
        result = await call_tool(name, arguments)
        return [types.TextContent(type="text", text=json.dumps(result))]

    async with mcp.server.stdio.stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())

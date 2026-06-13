# psu-mcp

MCP server for programmable bench PSU control with autonomous bootloader-entry probing.

MVP: Korad KA3005P / RND 320-KA3005P. Vendor-extensible via `vendors.py` strategy registry.

## Why

- Hardware security engagements often hinge on getting a target into bootloader mode via a precisely-timed power cycle. Doing this manually is error-prone and unrepeatable.
- An agent driving the PSU over MCP can sweep timings autonomously, observe the post-restore current curve, and converge on a working pattern.
- Removes a human-in-the-loop step from BK7231/ESP-class extraction workflows.

## Tools

| Tool | Tier | Purpose |
|------|------|---------|
| `connect` | read-only | Probe PSU, verify declared profiles against live VSET |
| `list_profiles` | read-only | Return operator-declared profile slot labels |
| `get_status` | read-only | Live VSET/ISET/VOUT/IOUT/output_on and declared profiles; warns if VSET does not match any declared profile |
| `recall_profile` | allowed-write | Load operator-declared profile slot N. Refuses slots not in config. Forces output_off on profile mismatch |
| `output_on` | allowed-write | Enable output. Refuses if live VSET does not match any declared profile |
| `output_off` | allowed-write | Disable output |
| `yank_restore` | allowed-write | Atomic power cycle (with optional `repeat`); refuses if VSET is not in a declared profile |
| `pulse_off_observe` | allowed-write | Power cycle + telemetry sample of restore curve; same VSET pre-flight |

## Safety model

Two tiers in active use:

- **read-only**: full autonomy
- **allowed-write**: autonomous, logged

`APPROVAL_WRITE` exists in the tier enum but no MVP tools live there. There is no MCP-side voltage or current setter -- the agent cannot fire a voltage at a target that the operator did not deliberately pre-load into a memory slot.

### Profile-as-protection (the only contract)

The operator pre-loads memory slots M1-M5 on the PSU at the bench (slow, deliberate, physical). The agent picks a profile slot -- it never picks a voltage. Voltage authority is a hand on a knob, not a software config value.

Output-affecting tools (`output_on`, `yank_restore`, `pulse_off_observe`) verify at entry that the live VSET equals one of the operator-declared profile mv values. A stray VSET (panel knob, post-power-cycle default, prior session) does not satisfy this check; the tool refuses until the agent calls `recall_profile`.

`recall_profile` only accepts slots that are declared in config. The post-recall VSET is verified against the declared mv; mismatch forces `output_off` if it was on. `SAV{n}` is not exposed at all -- profile contents are operator authority.

Pre-flight checks happen at tool entry. The `yank_restore` and `pulse_off_observe` timed cycles are atomic against the agent -- no checks during the window. Operator discipline carries the rest: do not touch the panel during a sequence.

## Installation

```bash
pip install -e ".[dev]"
```

System requirement: user must be in the `dialout` group for serial access:

```bash
sudo usermod -aG dialout $USER
# log out and back in for group membership to take effect
```

## Configuration

First-time setup: copy `config.example.json` to wherever you want it and edit to match the M1-M5 slot labels you have physically loaded on the PSU panel:

```bash
mkdir -p ~/.config/psu-mcp
cp config.example.json ~/.config/psu-mcp/config.json
$EDITOR ~/.config/psu-mcp/config.json
```

The MCP reads `PSU_CONFIG_PATH` at startup. Changing the file mid-session does not take effect until the MCP restarts.

Schema:

```json
{
  "port": "/dev/ttyACM0",
  "vendor": "korad_ka3005p",
  "profiles": {
    "1": {"mv": 3300, "label": "BK7231"},
    "2": {"mv": 3300, "label": "ESP_logic"},
    "3": {"mv": 5000, "label": "ESP_via_USB"},
    "4": {"mv": 1800, "label": "core_logic"},
    "5": {"mv": 2500, "label": "spare"}
  }
}
```

`profiles` must declare at least one slot. There is no separate `max_voltage_mv` / `max_current_ma` setting -- the set of declared profile mv values is the implicit allowlist, and the operator's physical M-slot load is the authoritative source.

### MCP client (.mcp.json)

```json
{
  "mcpServers": {
    "psu": {
      "command": "/path/to/.venv/bin/python",
      "args": ["-m", "psu_mcp"],
      "env": {
        "PSU_CONFIG_PATH": "/home/you/.config/psu-mcp/config.json"
      }
    }
  }
}
```

## Engagement logging (optional)

`yank_restore` and `pulse_off_observe` accept optional `engagement_name` and `project_path` arguments. When either is provided, the tool appends a JSONL line per invocation to `<engagement>/uart/logs/psu.jsonl`. The line includes the full result payload -- cycle log for yanks, telemetry array for pulse observations -- so the engagement folder accumulates raw data for later analysis (chip-family signature library, post-mortem evidence, drift detection).

Resolution rules:

- `project_path` (absolute) -> `<project_path>/uart/logs/psu.jsonl`
- `engagement_name` -> `$PIDEV_ENGAGEMENTS_DIR/<engagement_name>/uart/logs/psu.jsonl`
- Both provided -> `project_path` wins
- Neither provided -> no log; tool returns payload only

Set `PIDEV_ENGAGEMENTS_DIR` in the MCP client config:

```json
{
  "psu": {
    "command": "/path/to/.venv/bin/python",
    "args": ["-m", "psu_mcp"],
    "env": {
      "PSU_CONFIG_PATH": "/home/you/.config/psu-mcp/config.json",
      "PIDEV_ENGAGEMENTS_DIR": "/home/you/engagements"
    }
  }
}
```

If `engagement_name` is requested but the env var is not set, the tool returns successfully and adds a warning to `result["warnings"]` (the probe already happened; logging failure does not abort it).

Resolution: 10 Hz max sampling on `pulse_off_observe` -- enough for steady-state classification and curve-shape archival, not for sub-millisecond waveform analysis. See the spec for the trade-off discussion.

## Operator notes

- Do not touch the panel during a yank or pulse sequence. The cycle is atomic against the agent but not against a hand on the M-buttons.
- KA3005P firmware has no remote-lock. Last command wins between panel and serial.
- `connect` skips profile verification if output is on -- recalling each slot would whipsaw the live voltage. Call `output_off` first.
- If you change a profile mv at the bench (e.g., reload M3 from 5000 to 3300), update the config to match before the next engagement. The MCP loads config at startup, so changes require a restart.
- **Timing bias on `yank_restore`:** each cycle adds ~31 ms of Korad serial settle overhead per output-state transition (write + ~30 ms post-write delay in `protocol.py`). Requesting `off_ms=1500` produces `off_ms_actual` of ~1531 ms; the bias is consistent and deterministic. Account for it if you are tuning timing windows against a HITL retry loop -- the actual time the chip spends without power is what the chip sees, not the requested value.
- **Bootloader entry check via current readback:** after a yank, call `get_status` and read `iout_ma`. <15 mA = chip is in ROM bootloader (low quiescent, listening on UART). 40-70 mA = app firmware still running (yank failed, substrate parasitic-hold suspect on FT232/CH340 dongles -- try larger `off_ms`). ~0 mA + low `vout_mv` = chip did not power back up (yank too long). This is a free side-channel that does not need UART access.

## Tests

```bash
pytest                          # 129 unit tests, no hardware needed
pytest tests/ -m hardware       # 6 integration tests, real KA3005P required
```

The hardware suite expects the PSU panel slot 1 to be loaded with 3300 mV; the test fixture declares a single profile to match. Override the port with `PSU_TEST_PORT=/dev/ttyACMx`.

## License

MIT

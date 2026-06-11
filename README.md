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
| `get_status` | read-only | Live VSET/ISET/VOUT/IOUT/output_on with bounds + warnings |
| `recall_profile` | allowed-write | Load profile slot N; forces output_off on bound violation |
| `set_voltage` | approval-write | Set VSET (requires `_confirmed` token) |
| `set_current_limit` | allowed-write | Set ISET |
| `output_on` | allowed-write | Enable output (pre-flight bounds check) |
| `output_off` | allowed-write | Disable output |
| `yank_restore` | allowed-write | Atomic power cycle (with optional `repeat`) |
| `pulse_off_observe` | allowed-write | Power cycle + telemetry sample of restore curve |

## Safety model

Three tiers:

- **read-only**: full autonomy
- **allowed-write**: autonomous, logged
- **approval-write**: requires `_confirmed` token; voltage bounds always enforced

Configured bounds (`max_voltage_mv`, `max_current_ma`) are pre-flight checked at tool entry for every output-affecting tool. Bounds checks are NOT interleaved with the timed cycle in `yank_restore`/`pulse_off_observe` -- the cycle is atomic to preserve yank timing.

### Profile-as-protection

The operator pre-loads memory slots M1-M5 on the PSU at the bench (slow, deliberate, physical). The agent never picks a voltage -- it picks a profile slot. Voltage authority is a hand on a knob, not a software config value. `set_voltage` is kept as an escape hatch (approval-write) for unprofiled chips.

`RCL{n}` is exposed only via `recall_profile`. `SAV{n}` is not exposed at all -- profile contents are operator authority.

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

Set `PSU_CONFIG_PATH` to a JSON file:

```json
{
  "port": "/dev/ttyACM0",
  "vendor": "korad_ka3005p",
  "max_voltage_mv": 5000,
  "max_current_ma": 1000,
  "profiles": {
    "1": {"mv": 3300, "label": "BK7231"},
    "2": {"mv": 3300, "label": "ESP_logic"},
    "3": {"mv": 5000, "label": "ESP_via_USB"},
    "4": {"mv": 1800, "label": "core_logic"},
    "5": {"mv": 2500, "label": "spare"}
  }
}
```

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

## Operator notes

- Do not touch the panel during a yank or pulse sequence. The cycle is atomic against the agent but not against a hand on the M-buttons.
- KA3005P firmware has no remote-lock. Last command wins between panel and serial.
- `connect` skips profile verification if output is on -- recalling each slot would whipsaw the live voltage. Call `output_off` first.

## Tests

```bash
pytest                          # ~118 tests, no hardware needed
pytest tests/ -m hardware       # integration tests, real KA3005P required
```

## License

MIT

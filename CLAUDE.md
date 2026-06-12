# CLAUDE.md -- psu-mcp

This file is agent orientation for the psu-mcp submodule.

## Project

psu-mcp wraps a Korad-protocol bench PSU as MCP tools for power control and autonomous bootloader-entry probing. MVP target: Korad KA3005P / RND 320-KA3005P. Vendor-extensible via `vendors.py`.

Design spec: `../../docs/superpowers/specs/2026-06-11-psu-mcp-design.md`

## Architecture

```
Skills (psu-probe, ltchiptool-probe, uart-probe)
  |
  MCP boundary
  |
psu-mcp (Python, stdio transport)
  |
  +-- session.py (per-call + persistent serial context managers)
  |     |
  |     +-- protocol.py (ONLY module that imports pyserial)
  |           |
  |           Korad text protocol -> USB CDC serial -> PSU
  |
  +-- telemetry.py (asyncio sampler for pulse_off_observe)
  |
  +-- safety.py (tier classification + bounds enforcement)
  +-- profiles.py (config + declared slot verification)
  +-- vendors.py (per-vendor strategy registry)
```

Single-owner principle: protocol.py is the only module that touches pyserial. session.py wraps it in asyncio.to_thread for the async tool layer.

## Safety tiers

- **read-only**: `connect`, `list_profiles`, `get_status`
- **allowed-write**: `recall_profile`, `output_on`, `output_off`, `yank_restore`, `pulse_off_observe`
- **approval-write**: (no tools in MVP)

No MCP-side voltage or current setter. The agent has zero authority to fire a voltage that the operator did not deliberately load into a memory slot. Pre-flight checks at tool entry verify the live VSET matches one of the declared profile mv values; output-affecting tools refuse otherwise. The yank/pulse cycle is atomic -- no checks during the timed window.

## Profile-as-protection (the only contract)

The operator pre-loads M1-M5 at the bench. The agent picks a declared profile slot. Voltage authority is hardware, not config.

`SAV{n}` is not exposed; the agent must not silently save new setpoints into operator-owned slots. `recall_profile` only accepts slots declared in config -- the agent cannot recall an undeclared slot.

## Engagement logging

`yank_restore` and `pulse_off_observe` take optional `engagement_name` / `project_path` parameters. When provided, the tool appends a JSONL line per invocation to `<engagement>/uart/logs/psu.jsonl` -- pattern matches buspirate/ltchiptool/pm3. `PIDEV_ENGAGEMENTS_DIR` env var resolves engagement_name. Each line includes the full result payload, including the raw telemetry array for pulse_off_observe, for downstream corpus / drift detection / forensic use. Logging failures emit warnings rather than aborting the probe (the side-channel data is bonus, not the contract).

## Style

- Python 3.11 minimum
- No emojis, no em-dashes
- Commit messages: short, to the point, no co-author footers
- Cynicism welcome in commits and docs

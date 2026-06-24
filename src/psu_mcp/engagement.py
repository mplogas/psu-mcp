"""Optional engagement logging for probing tools.

When `engagement_name` or `engagement_path` is provided to yank_restore or
pulse_off_observe, the tool appends a JSONL line describing the call to
`<engagement>/uart/logs/psu.jsonl`. This mirrors the pattern from
buspirate-mcp, ltchiptool-mcp, and pm3-mcp -- psu output lands alongside
UART artifacts so the engagement folder tells one cohesive story.

Resolution:
  - engagement_path  -> <engagement_path>/uart/logs/psu.jsonl
  - engagement_name          -> <PIDEV_ENGAGEMENTS_DIR>/<engagement_name>/uart/logs/psu.jsonl
  - neither                  -> no log (tool stays a primitive)

If logging is requested but writing fails (permissions, disk, missing env),
the tool result still returns the structured payload. A warning is added
to result["warnings"] explaining the failure. The probe already happened;
losing the log is not worth aborting.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


_LOG_SUBPATH = ("uart", "logs", "psu.jsonl")


class EngagementLoggingError(RuntimeError):
    """Raised by resolve_log_path when configuration is inconsistent."""


def resolve_log_path(
    engagement_name: str | None,
    engagement_path: str | None,
) -> Path | None:
    """Resolve where the JSONL log should go, or None if not requested.

    engagement_path wins if both are provided. Raises EngagementLoggingError
    if engagement_name is set but PIDEV_ENGAGEMENTS_DIR is not.
    """
    if engagement_path:
        base = Path(engagement_path)
    elif engagement_name:
        env_dir = os.environ.get("PIDEV_ENGAGEMENTS_DIR")
        if not env_dir:
            raise EngagementLoggingError(
                "engagement_name provided but PIDEV_ENGAGEMENTS_DIR env var "
                "is not set"
            )
        base = Path(env_dir) / engagement_name
    else:
        return None
    return base.joinpath(*_LOG_SUBPATH)


def append_log_line(path: Path, entry: dict) -> None:
    """Append a single JSONL line. Creates parent dirs as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry, separators=(",", ":"), default=str)
    with path.open("a") as f:
        f.write(line + "\n")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

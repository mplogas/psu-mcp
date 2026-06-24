import json
from pathlib import Path

import pytest

from psu_mcp.engagement import (
    EngagementLoggingError,
    append_log_line,
    now_iso,
    resolve_log_path,
)


class TestResolveLogPath:
    def test_neither_returns_none(self, monkeypatch):
        monkeypatch.delenv("PIDEV_ENGAGEMENTS_DIR", raising=False)
        assert resolve_log_path(None, None) is None

    def test_engagement_path_wins(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PIDEV_ENGAGEMENTS_DIR", str(tmp_path / "engagements"))
        result = resolve_log_path(
            engagement_name="ignored", engagement_path=str(tmp_path / "project_x")
        )
        assert result == tmp_path / "project_x" / "uart" / "logs" / "psu.jsonl"

    def test_engagement_name_uses_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PIDEV_ENGAGEMENTS_DIR", str(tmp_path / "engagements"))
        result = resolve_log_path(engagement_name="2026-06-12-bench", engagement_path=None)
        assert result == (
            tmp_path / "engagements" / "2026-06-12-bench" / "uart" / "logs" / "psu.jsonl"
        )

    def test_engagement_name_without_env_raises(self, monkeypatch):
        monkeypatch.delenv("PIDEV_ENGAGEMENTS_DIR", raising=False)
        with pytest.raises(EngagementLoggingError, match="PIDEV_ENGAGEMENTS_DIR"):
            resolve_log_path(engagement_name="x", engagement_path=None)


class TestAppendLogLine:
    def test_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "deep" / "nested" / "psu.jsonl"
        append_log_line(path, {"foo": "bar"})
        assert path.exists()

    def test_writes_jsonl_line(self, tmp_path):
        path = tmp_path / "psu.jsonl"
        append_log_line(path, {"tool": "yank_restore", "ok": True})
        content = path.read_text()
        line = content.rstrip("\n")
        assert json.loads(line) == {"tool": "yank_restore", "ok": True}
        assert content.endswith("\n")

    def test_appends_not_overwrites(self, tmp_path):
        path = tmp_path / "psu.jsonl"
        append_log_line(path, {"n": 1})
        append_log_line(path, {"n": 2})
        lines = path.read_text().strip().split("\n")
        assert [json.loads(line) for line in lines] == [{"n": 1}, {"n": 2}]


class TestNowIso:
    def test_returns_zulu_timestamp(self):
        ts = now_iso()
        assert ts.endswith("Z")
        assert "T" in ts

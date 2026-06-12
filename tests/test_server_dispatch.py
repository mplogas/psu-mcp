from unittest.mock import AsyncMock, patch

import pytest

from psu_mcp.server import call_tool, TOOL_DEFINITIONS, _load_config_from_env


class TestToolDefinitions:
    def test_all_eight_tools_defined(self):
        names = {t.name for t in TOOL_DEFINITIONS}
        assert names == {
            "connect",
            "list_profiles",
            "get_status",
            "recall_profile",
            "output_on",
            "output_off",
            "yank_restore",
            "pulse_off_observe",
        }

    def test_set_voltage_not_defined(self):
        names = {t.name for t in TOOL_DEFINITIONS}
        assert "set_voltage" not in names

    def test_set_current_limit_not_defined(self):
        names = {t.name for t in TOOL_DEFINITIONS}
        assert "set_current_limit" not in names


class TestCallToolDispatch:
    @pytest.mark.parametrize("tool_name,patch_target", [
        ("connect", "psu_mcp.server.tool_connect"),
        ("list_profiles", "psu_mcp.server.tool_list_profiles"),
        ("get_status", "psu_mcp.server.tool_get_status"),
        ("recall_profile", "psu_mcp.server.tool_recall_profile"),
        ("output_on", "psu_mcp.server.tool_output_on"),
        ("output_off", "psu_mcp.server.tool_output_off"),
        ("yank_restore", "psu_mcp.server.tool_yank_restore"),
        ("pulse_off_observe", "psu_mcp.server.tool_pulse_off_observe"),
    ])
    async def test_dispatches_to_named_tool(
        self, tool_name, patch_target, psu_config
    ):
        with patch(patch_target, new=AsyncMock(return_value={"ok": True})) as mock:
            with patch(
                "psu_mcp.server._load_config_from_env", return_value=psu_config
            ):
                args = self._args_for(tool_name)
                result = await call_tool(tool_name, args)
            mock.assert_called_once()
        assert result["ok"] is True

    def _args_for(self, tool_name: str) -> dict:
        return {
            "connect": {},
            "list_profiles": {},
            "get_status": {},
            "recall_profile": {"slot": 1},
            "output_on": {},
            "output_off": {},
            "yank_restore": {"off_ms": 100},
            "pulse_off_observe": {"off_ms": 100, "observe_ms": 200},
        }[tool_name]

    async def test_unknown_tool_returns_error(self, psu_config):
        with patch(
            "psu_mcp.server._load_config_from_env", return_value=psu_config
        ):
            result = await call_tool("does_not_exist", {})
        assert result["ok"] is False
        assert result["error"] == "unknown_tool"


class TestConfigLoading:
    def test_config_path_from_env(self, tmp_path, monkeypatch):
        cfg = tmp_path / "psu.json"
        cfg.write_text(
            '{"port":"/dev/ttyACM0","vendor":"korad_ka3005p",'
            '"profiles":{"1":{"mv":3300,"label":"BK7231"}}}'
        )
        monkeypatch.setenv("PSU_CONFIG_PATH", str(cfg))
        c = _load_config_from_env()
        assert c.port == "/dev/ttyACM0"

    def test_missing_env_raises(self, monkeypatch):
        monkeypatch.delenv("PSU_CONFIG_PATH", raising=False)
        with pytest.raises(RuntimeError, match="PSU_CONFIG_PATH"):
            _load_config_from_env()

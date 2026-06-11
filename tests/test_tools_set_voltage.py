import pytest

from psu_mcp.tools import tool_set_voltage


_CONFIRM = "I understand the voltage risk"


class TestSetVoltage:
    async def test_requires_confirmation(self, with_psu, psu_config):
        result = await tool_set_voltage(psu_config, voltage_mv=3300)
        assert result["ok"] is False
        assert result["error"] == "confirmation_required"

    async def test_with_confirmation_sets_voltage(self, with_psu, psu_config):
        result = await tool_set_voltage(
            psu_config, voltage_mv=3300, _confirmed=_CONFIRM
        )
        assert result["ok"] is True
        assert result["vset_mv"] == 3300
        assert with_psu.vset_mv == 3300

    async def test_rejects_above_bound_even_with_confirmation(
        self, with_psu, psu_config
    ):
        result = await tool_set_voltage(
            psu_config, voltage_mv=6000, _confirmed=_CONFIRM
        )
        assert result["ok"] is False
        assert result["error"] == "bounds_exceeded"
        assert with_psu.vset_mv != 6000

    async def test_voltage_at_bound_is_accepted(self, with_psu, psu_config):
        result = await tool_set_voltage(
            psu_config, voltage_mv=5000, _confirmed=_CONFIRM
        )
        assert result["ok"] is True
        assert with_psu.vset_mv == 5000

    async def test_negative_voltage_rejected(self, with_psu, psu_config):
        result = await tool_set_voltage(
            psu_config, voltage_mv=-1, _confirmed=_CONFIRM
        )
        assert result["ok"] is False
        assert result["error"] == "invalid_argument"

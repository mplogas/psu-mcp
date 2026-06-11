import pytest

from psu_mcp.tools import (
    tool_set_current_limit,
    tool_output_on,
    tool_output_off,
    tool_recall_profile,
)


class TestSetCurrentLimit:
    async def test_sets_value(self, with_psu, psu_config):
        result = await tool_set_current_limit(psu_config, current_ma=500)
        assert result["ok"] is True
        assert result["iset_ma"] == 500
        assert with_psu.iset_ma == 500

    async def test_rejects_above_bound(self, with_psu, psu_config):
        result = await tool_set_current_limit(psu_config, current_ma=2000)
        assert result["ok"] is False
        assert result["error"] == "bounds_exceeded"
        assert with_psu.iset_ma != 2000

    async def test_negative_rejected(self, with_psu, psu_config):
        result = await tool_set_current_limit(psu_config, current_ma=-1)
        assert result["ok"] is False
        assert result["error"] == "invalid_argument"


class TestOutputOn:
    async def test_enables_output_when_safe(self, with_psu, psu_config):
        with_psu.vset_mv = 3300
        with_psu.iset_ma = 500
        with_psu.output_on = False
        result = await tool_output_on(psu_config)
        assert result["ok"] is True
        assert with_psu.output_on is True

    async def test_rejects_when_vset_exceeds_bound(self, with_psu, psu_config):
        with_psu.vset_mv = 6000  # exceeds 5000
        with_psu.output_on = False
        result = await tool_output_on(psu_config)
        assert result["ok"] is False
        assert result["error"] == "bounds_exceeded_pre_flight"
        assert with_psu.output_on is False

    async def test_rejects_when_iset_exceeds_bound(self, with_psu, psu_config):
        with_psu.vset_mv = 3300
        with_psu.iset_ma = 2000  # exceeds 1000
        with_psu.output_on = False
        result = await tool_output_on(psu_config)
        assert result["ok"] is False
        assert result["error"] == "bounds_exceeded_pre_flight"
        assert with_psu.output_on is False


class TestOutputOff:
    async def test_disables_output(self, with_psu, psu_config):
        with_psu.output_on = True
        result = await tool_output_off(psu_config)
        assert result["ok"] is True
        assert with_psu.output_on is False

    async def test_idempotent_when_already_off(self, with_psu, psu_config):
        with_psu.output_on = False
        result = await tool_output_off(psu_config)
        assert result["ok"] is True
        assert with_psu.output_on is False


class TestRecallProfile:
    async def test_recalls_and_returns_loaded_value(self, with_psu, psu_config):
        with_psu.profiles[1] = 3300
        result = await tool_recall_profile(psu_config, slot=1)
        assert result["ok"] is True
        assert result["loaded_vset_mv"] == 3300
        assert with_psu.vset_mv == 3300

    async def test_rejects_slot_out_of_range(self, with_psu, psu_config):
        result = await tool_recall_profile(psu_config, slot=6)
        assert result["ok"] is False
        assert result["error"] == "slot_invalid"

    async def test_bounds_violation_forces_output_off(self, with_psu, psu_config):
        # Output is on, profile 3 declares 5000mv but FakePSU has it at 6000mv
        with_psu.output_on = True
        with_psu.vset_mv = 3300
        with_psu.profiles[3] = 6000  # exceeds bound of 5000
        result = await tool_recall_profile(psu_config, slot=3)
        assert result["ok"] is False
        assert result["error"] == "bounds_exceeded_post_recall"
        assert with_psu.output_on is False  # forced off

    async def test_bounds_violation_with_output_already_off(self, with_psu, psu_config):
        with_psu.output_on = False
        with_psu.profiles[3] = 6000
        result = await tool_recall_profile(psu_config, slot=3)
        assert result["ok"] is False
        assert result["error"] == "bounds_exceeded_post_recall"
        assert with_psu.output_on is False

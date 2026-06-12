import pytest

from psu_mcp.tools import (
    tool_output_on,
    tool_output_off,
    tool_recall_profile,
)


class TestOutputOn:
    async def test_enables_output_when_vset_matches_profile(self, with_psu, psu_config):
        # psu_config declares profiles with mv values {3300, 5000}.
        with_psu.vset_mv = 3300
        with_psu.output_on = False
        result = await tool_output_on(psu_config)
        assert result["ok"] is True
        assert with_psu.output_on is True
        assert result["vset_mv"] == 3300

    async def test_refuses_when_vset_does_not_match_any_profile(
        self, with_psu, psu_config
    ):
        # 4000 mV is not in {3300, 5000}
        with_psu.vset_mv = 4000
        with_psu.output_on = False
        result = await tool_output_on(psu_config)
        assert result["ok"] is False
        assert result["error"] == "vset_unrecognized"
        assert with_psu.output_on is False
        assert result["details"]["vset_mv"] == 4000

    async def test_refuses_at_zero(self, with_psu, psu_config):
        with_psu.vset_mv = 0
        with_psu.output_on = False
        result = await tool_output_on(psu_config)
        assert result["ok"] is False
        assert result["error"] == "vset_unrecognized"


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
        # Slot 1 declared as 3300mv, FakePSU also has slot 1 at 3300.
        with_psu.profiles[1] = 3300
        result = await tool_recall_profile(psu_config, slot=1)
        assert result["ok"] is True
        assert result["loaded_vset_mv"] == 3300
        assert result["label"] == "BK7231"
        assert with_psu.vset_mv == 3300

    async def test_rejects_slot_out_of_range(self, with_psu, psu_config):
        result = await tool_recall_profile(psu_config, slot=6)
        assert result["ok"] is False
        assert result["error"] == "slot_invalid"

    async def test_rejects_slot_not_declared(self, with_psu, psu_config):
        # psu_config only declares slots 1, 2, 3. Slot 4 is in PSU range
        # but not declared.
        result = await tool_recall_profile(psu_config, slot=4)
        assert result["ok"] is False
        assert result["error"] == "slot_not_declared"

    async def test_profile_mismatch_forces_output_off(self, with_psu, psu_config):
        # Output is on, declared slot 1 is 3300mv but FakePSU has it at 6000mv.
        with_psu.output_on = True
        with_psu.vset_mv = 3300
        with_psu.profiles[1] = 6000  # mismatches declared
        result = await tool_recall_profile(psu_config, slot=1)
        assert result["ok"] is False
        assert result["error"] == "profile_mismatch"
        assert with_psu.output_on is False  # forced off

    async def test_profile_mismatch_with_output_already_off(
        self, with_psu, psu_config
    ):
        with_psu.output_on = False
        with_psu.profiles[1] = 6000
        result = await tool_recall_profile(psu_config, slot=1)
        assert result["ok"] is False
        assert result["error"] == "profile_mismatch"
        assert with_psu.output_on is False

import pytest

from psu_mcp.safety import (
    SafetyTier,
    classify_tool,
    vset_matches_declared_profile,
)


class TestClassifyTool:
    @pytest.mark.parametrize("name", ["connect", "list_profiles", "get_status"])
    def test_read_only_tools(self, name):
        assert classify_tool(name) == SafetyTier.READ_ONLY

    @pytest.mark.parametrize("name", [
        "recall_profile",
        "output_on",
        "output_off",
        "yank_restore",
        "pulse_off_observe",
    ])
    def test_allowed_write_tools(self, name):
        assert classify_tool(name) == SafetyTier.ALLOWED_WRITE

    def test_unknown_tool_raises(self):
        with pytest.raises(ValueError, match="Unknown tool"):
            classify_tool("does_not_exist")

    def test_set_voltage_is_no_longer_a_tool(self):
        with pytest.raises(ValueError, match="Unknown tool"):
            classify_tool("set_voltage")

    def test_set_current_limit_is_no_longer_a_tool(self):
        with pytest.raises(ValueError, match="Unknown tool"):
            classify_tool("set_current_limit")


class TestVsetMatchesDeclaredProfile:
    def test_match_returns_true(self):
        assert vset_matches_declared_profile(3300, {3300, 5000}) is True

    def test_no_match_returns_false(self):
        assert vset_matches_declared_profile(4000, {3300, 5000}) is False

    def test_empty_declared_set_returns_false(self):
        assert vset_matches_declared_profile(3300, set()) is False

    def test_zero_does_not_match_nonempty(self):
        assert vset_matches_declared_profile(0, {3300}) is False

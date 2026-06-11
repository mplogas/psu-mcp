import pytest

from psu_mcp.safety import (
    SafetyTier,
    classify_tool,
    Bounds,
    check_voltage_bound,
    check_current_bound,
    BoundsError,
)


class TestClassifyTool:
    @pytest.mark.parametrize("name", ["connect", "list_profiles", "get_status"])
    def test_read_only_tools(self, name):
        assert classify_tool(name) == SafetyTier.READ_ONLY

    @pytest.mark.parametrize("name", [
        "recall_profile",
        "set_current_limit",
        "output_on",
        "output_off",
        "yank_restore",
        "pulse_off_observe",
    ])
    def test_allowed_write_tools(self, name):
        assert classify_tool(name) == SafetyTier.ALLOWED_WRITE

    def test_set_voltage_is_approval_write(self):
        assert classify_tool("set_voltage") == SafetyTier.APPROVAL_WRITE

    def test_unknown_tool_raises(self):
        with pytest.raises(ValueError, match="Unknown tool"):
            classify_tool("does_not_exist")


class TestBoundsChecks:
    def test_voltage_within_bound_returns_value(self):
        b = Bounds(max_voltage_mv=5000, max_current_ma=1000)
        assert check_voltage_bound(3300, b) == 3300

    def test_voltage_at_bound_returns_value(self):
        b = Bounds(max_voltage_mv=5000, max_current_ma=1000)
        assert check_voltage_bound(5000, b) == 5000

    def test_voltage_exceeds_bound_raises(self):
        b = Bounds(max_voltage_mv=3300, max_current_ma=1000)
        with pytest.raises(BoundsError) as ei:
            check_voltage_bound(5000, b)
        assert "voltage" in str(ei.value).lower()
        assert "5000" in str(ei.value)
        assert "3300" in str(ei.value)

    def test_current_within_bound_returns_value(self):
        b = Bounds(max_voltage_mv=5000, max_current_ma=1000)
        assert check_current_bound(500, b) == 500

    def test_current_exceeds_bound_raises(self):
        b = Bounds(max_voltage_mv=5000, max_current_ma=500)
        with pytest.raises(BoundsError):
            check_current_bound(1000, b)

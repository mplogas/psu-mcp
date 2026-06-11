import pytest

from psu_mcp.tools import tool_yank_restore


class TestYankRestore:
    async def test_single_cycle_default(self, with_psu, psu_config):
        with_psu.vset_mv = 3300
        with_psu.iset_ma = 500
        with_psu.output_on = True
        result = await tool_yank_restore(psu_config, off_ms=100)
        assert result["ok"] is True
        assert len(result["cycles"]) == 1
        # Output ends ON after a yank_restore by definition
        assert with_psu.output_on is True

    async def test_repeat_runs_n_cycles(self, with_psu, psu_config):
        with_psu.vset_mv = 3300
        with_psu.iset_ma = 500
        with_psu.output_on = True
        result = await tool_yank_restore(
            psu_config, off_ms=80, on_ms=60, repeat=3
        )
        assert result["ok"] is True
        assert len(result["cycles"]) == 3

    async def test_cycle_log_has_actual_timings(self, with_psu, psu_config):
        with_psu.vset_mv = 3300
        result = await tool_yank_restore(
            psu_config, off_ms=100, on_ms=50, repeat=1
        )
        cycle = result["cycles"][0]
        assert "off_ms_actual" in cycle
        assert "on_ms_actual" in cycle
        assert cycle["off_ms_actual"] >= 100
        assert cycle["on_ms_actual"] >= 50

    async def test_pre_flight_bounds_rejection(self, with_psu, psu_config):
        with_psu.vset_mv = 6000  # exceeds 5000
        with_psu.output_on = True
        result = await tool_yank_restore(psu_config, off_ms=100)
        assert result["ok"] is False
        assert result["error"] == "bounds_exceeded_pre_flight"
        # The PSU should not have been cycled; output still on
        assert with_psu.output_on is True

    async def test_repeat_gt_1_requires_on_ms(self, with_psu, psu_config):
        with_psu.vset_mv = 3300
        result = await tool_yank_restore(
            psu_config, off_ms=100, on_ms=0, repeat=2
        )
        assert result["ok"] is False
        assert result["error"] == "sanity_violation"
        assert "on_ms" in result["message"]

    async def test_negative_off_ms_rejected(self, with_psu, psu_config):
        result = await tool_yank_restore(psu_config, off_ms=-1)
        assert result["ok"] is False
        assert result["error"] == "invalid_argument"

    async def test_zero_repeat_rejected(self, with_psu, psu_config):
        result = await tool_yank_restore(psu_config, off_ms=100, repeat=0)
        assert result["ok"] is False
        assert result["error"] == "invalid_argument"

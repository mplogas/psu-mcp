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

    async def test_pre_flight_refuses_unrecognized_vset(self, with_psu, psu_config):
        # 4000 mV is not in declared profiles {3300, 5000}
        with_psu.vset_mv = 4000
        with_psu.output_on = True
        result = await tool_yank_restore(psu_config, off_ms=100)
        assert result["ok"] is False
        assert result["error"] == "vset_unrecognized"
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


class TestYankRestoreLogging:
    async def test_no_log_when_engagement_not_provided(
        self, with_psu, psu_config, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("PIDEV_ENGAGEMENTS_DIR", str(tmp_path))
        with_psu.vset_mv = 3300
        result = await tool_yank_restore(psu_config, off_ms=80)
        assert result["ok"] is True
        # No engagement dir touched
        assert list(tmp_path.iterdir()) == []

    async def test_logs_to_engagement_dir(
        self, with_psu, psu_config, tmp_path, monkeypatch
    ):
        import json

        monkeypatch.setenv("PIDEV_ENGAGEMENTS_DIR", str(tmp_path))
        with_psu.vset_mv = 3300
        result = await tool_yank_restore(
            psu_config, off_ms=80, engagement_name="bench-2026-06-12"
        )
        assert result["ok"] is True
        log_path = tmp_path / "bench-2026-06-12" / "uart" / "logs" / "psu.jsonl"
        assert log_path.exists()
        entry = json.loads(log_path.read_text().strip())
        assert entry["tool"] == "yank_restore"
        assert entry["args"]["off_ms"] == 80
        assert entry["result"]["ok"] is True
        assert len(entry["result"]["cycles"]) == 1

    async def test_logs_to_engagement_path(
        self, with_psu, psu_config, tmp_path, monkeypatch
    ):
        import json

        monkeypatch.delenv("PIDEV_ENGAGEMENTS_DIR", raising=False)
        with_psu.vset_mv = 3300
        project = tmp_path / "my-project"
        result = await tool_yank_restore(
            psu_config, off_ms=80, engagement_path=str(project)
        )
        assert result["ok"] is True
        log_path = project / "uart" / "logs" / "psu.jsonl"
        assert log_path.exists()
        entry = json.loads(log_path.read_text().strip())
        assert entry["tool"] == "yank_restore"

    async def test_warns_when_engagement_name_without_env(
        self, with_psu, psu_config, monkeypatch
    ):
        monkeypatch.delenv("PIDEV_ENGAGEMENTS_DIR", raising=False)
        with_psu.vset_mv = 3300
        result = await tool_yank_restore(
            psu_config, off_ms=80, engagement_name="bench"
        )
        assert result["ok"] is True
        assert any("PIDEV_ENGAGEMENTS_DIR" in w for w in result.get("warnings", []))

    async def test_logs_failed_calls_too(
        self, with_psu, psu_config, tmp_path, monkeypatch
    ):
        import json

        monkeypatch.setenv("PIDEV_ENGAGEMENTS_DIR", str(tmp_path))
        with_psu.vset_mv = 4000  # not in declared profiles
        result = await tool_yank_restore(
            psu_config, off_ms=80, engagement_name="bench"
        )
        assert result["ok"] is False
        log_path = tmp_path / "bench" / "uart" / "logs" / "psu.jsonl"
        assert log_path.exists()
        entry = json.loads(log_path.read_text().strip())
        assert entry["result"]["error"] == "vset_unrecognized"

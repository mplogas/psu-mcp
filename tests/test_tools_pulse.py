import pytest

from psu_mcp.tools import tool_pulse_off_observe


class TestPulseOffObserve:
    async def test_returns_cycle_and_telemetry(self, with_psu, psu_config):
        with_psu.vset_mv = 3300
        with_psu.output_on = True
        result = await tool_pulse_off_observe(
            psu_config, off_ms=100, observe_ms=200, sample_interval_ms=50
        )
        assert result["ok"] is True
        assert "cycle" in result
        assert "telemetry" in result
        assert result["cycle"]["off_ms_requested"] == 100
        assert result["cycle"]["off_ms_actual"] >= 100

    async def test_telemetry_samples_have_required_keys(self, with_psu, psu_config):
        with_psu.vset_mv = 3300
        with_psu.output_on = True
        result = await tool_pulse_off_observe(
            psu_config, off_ms=80, observe_ms=150, sample_interval_ms=50
        )
        for s in result["telemetry"]:
            assert "t_ms" in s
            assert "vout_mv" in s
            assert "iout_ma" in s

    async def test_t_ms_monotonic(self, with_psu, psu_config):
        with_psu.vset_mv = 3300
        result = await tool_pulse_off_observe(
            psu_config, off_ms=50, observe_ms=200, sample_interval_ms=50
        )
        ts = [s["t_ms"] for s in result["telemetry"]]
        assert ts == sorted(ts)
        assert ts[0] == 0

    async def test_interval_too_fast_warns(self, with_psu, psu_config):
        with_psu.vset_mv = 3300
        result = await tool_pulse_off_observe(
            psu_config, off_ms=50, observe_ms=100, sample_interval_ms=10
        )
        warnings = result.get("warnings", [])
        assert any("sample_interval" in w.lower() for w in warnings)

    async def test_pre_flight_refuses_unrecognized_vset(self, with_psu, psu_config):
        # 4000 mV is not in declared profiles {3300, 5000}
        with_psu.vset_mv = 4000
        result = await tool_pulse_off_observe(
            psu_config, off_ms=100, observe_ms=200
        )
        assert result["ok"] is False
        assert result["error"] == "vset_unrecognized"

    async def test_negative_args_rejected(self, with_psu, psu_config):
        result = await tool_pulse_off_observe(
            psu_config, off_ms=-1, observe_ms=200
        )
        assert result["ok"] is False
        assert result["error"] == "invalid_argument"


class TestPulseOffObserveLogging:
    async def test_logs_telemetry_to_engagement_dir(
        self, with_psu, psu_config, tmp_path, monkeypatch
    ):
        import json

        monkeypatch.setenv("PIDEV_ENGAGEMENTS_DIR", str(tmp_path))
        with_psu.vset_mv = 3300
        result = await tool_pulse_off_observe(
            psu_config,
            off_ms=80,
            observe_ms=150,
            sample_interval_ms=50,
            engagement_name="bench",
        )
        assert result["ok"] is True
        log_path = tmp_path / "bench" / "uart" / "logs" / "psu.jsonl"
        assert log_path.exists()
        entry = json.loads(log_path.read_text().strip())
        assert entry["tool"] == "pulse_off_observe"
        # Full telemetry array is in the log entry, not just a summary
        assert len(entry["result"]["telemetry"]) >= 1
        assert entry["result"]["telemetry"][0]["t_ms"] == 0

"""Hardware integration tests. Run with:

    pytest tests/test_hardware.py -m hardware

Requires:
  - RND 320-KA3005P (or Korad KA3005P clone) connected via USB
  - Serial port path in PSU_TEST_PORT env var (defaults to /dev/ttyACM0)
  - User in dialout group
  - PSU output should be OFF at test start
  - Operator has pre-loaded slot 1 with 3300 mV at the bench

The hardware tests use slot 1 = 3300 mV as the only declared profile.
The PSU panel slot 1 must match this declaration, otherwise the profile
verification step in connect will warn and recall_profile will fail.
"""

import os

import pytest

from psu_mcp.profiles import PSUConfig, Profile
from psu_mcp.tools import (
    tool_connect,
    tool_get_status,
    tool_output_off,
    tool_output_on,
    tool_recall_profile,
    tool_yank_restore,
    tool_pulse_off_observe,
)


_PORT = os.environ.get("PSU_TEST_PORT", "/dev/ttyACM0")


@pytest.fixture
def config() -> PSUConfig:
    return PSUConfig(
        port=_PORT,
        vendor="korad_ka3005p",
        profiles={
            1: Profile(slot=1, mv=3300, label="bench_test"),
        },
    )


@pytest.mark.hardware
async def test_connect_returns_real_state(config):
    result = await tool_connect(config)
    assert result["ok"] is True
    assert result["vendor"] == "korad_ka3005p"


@pytest.mark.hardware
async def test_recall_profile_loads_declared_slot(config):
    result = await tool_recall_profile(config, slot=1)
    assert result["ok"] is True
    # KA3005P may round; allow 50 mV tolerance for hardware
    assert abs(result["loaded_vset_mv"] - 3300) <= 50


@pytest.mark.hardware
async def test_get_status_after_recall(config):
    await tool_recall_profile(config, slot=1)
    status = await tool_get_status(config)
    assert status["ok"] is True
    assert abs(status["vset_mv"] - 3300) <= 50


@pytest.mark.hardware
async def test_output_on_off_cycle(config):
    await tool_recall_profile(config, slot=1)
    on = await tool_output_on(config)
    assert on["ok"] is True
    off = await tool_output_off(config)
    assert off["ok"] is True


@pytest.mark.hardware
async def test_yank_restore_real(config):
    await tool_recall_profile(config, slot=1)
    await tool_output_on(config)
    result = await tool_yank_restore(config, off_ms=200, on_ms=100, repeat=1)
    assert result["ok"] is True
    assert result["cycles"][0]["off_ms_actual"] >= 200
    await tool_output_off(config)


@pytest.mark.hardware
async def test_pulse_off_observe_real(config):
    await tool_recall_profile(config, slot=1)
    await tool_output_on(config)
    result = await tool_pulse_off_observe(
        config, off_ms=200, observe_ms=500, sample_interval_ms=50
    )
    assert result["ok"] is True
    assert len(result["telemetry"]) >= 3
    await tool_output_off(config)

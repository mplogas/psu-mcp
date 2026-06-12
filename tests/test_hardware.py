"""Hardware integration tests. Run with:

    pytest tests/test_hardware.py -m hardware

Requires:
  - RND 320-KA3005P (or Korad KA3005P clone) connected via USB
  - Serial port path in PSU_TEST_PORT env var (defaults to /dev/ttyACM0)
  - User in dialout group
  - PSU output should be OFF at test start
"""

import os

import pytest

from psu_mcp.profiles import PSUConfig
from psu_mcp.tools import (
    tool_connect,
    tool_get_status,
    tool_output_off,
    tool_output_on,
    tool_set_current_limit,
    tool_set_voltage,
    tool_yank_restore,
    tool_pulse_off_observe,
)


_PORT = os.environ.get("PSU_TEST_PORT", "/dev/ttyACM0")
_CONFIRM = "I understand the voltage risk"


@pytest.fixture
def config() -> PSUConfig:
    return PSUConfig(
        port=_PORT,
        vendor="korad_ka3005p",
        max_voltage_mv=3300,
        max_current_ma=500,
        profiles={},
    )


@pytest.mark.hardware
async def test_connect_returns_real_state(config):
    result = await tool_connect(config)
    assert result["ok"] is True
    assert result["vendor"] == "korad_ka3005p"


@pytest.mark.hardware
async def test_set_voltage_and_readback(config):
    result = await tool_set_voltage(config, voltage_mv=3300, _confirmed=_CONFIRM)
    assert result["ok"] is True
    status = await tool_get_status(config)
    # KA3005P may round; allow 50mV tolerance for hardware
    assert abs(status["vset_mv"] - 3300) <= 50


@pytest.mark.hardware
async def test_set_current_and_readback(config):
    result = await tool_set_current_limit(config, current_ma=100)
    assert result["ok"] is True
    status = await tool_get_status(config)
    assert abs(status["iset_ma"] - 100) <= 5


@pytest.mark.hardware
async def test_output_on_off_cycle(config):
    await tool_set_voltage(config, voltage_mv=3300, _confirmed=_CONFIRM)
    on = await tool_output_on(config)
    assert on["ok"] is True
    off = await tool_output_off(config)
    assert off["ok"] is True


@pytest.mark.hardware
async def test_yank_restore_real(config):
    await tool_set_voltage(config, voltage_mv=3300, _confirmed=_CONFIRM)
    await tool_output_on(config)
    result = await tool_yank_restore(config, off_ms=200, on_ms=100, repeat=1)
    assert result["ok"] is True
    assert result["cycles"][0]["off_ms_actual"] >= 200
    await tool_output_off(config)


@pytest.mark.hardware
async def test_pulse_off_observe_real(config):
    await tool_set_voltage(config, voltage_mv=3300, _confirmed=_CONFIRM)
    await tool_output_on(config)
    result = await tool_pulse_off_observe(
        config, off_ms=200, observe_ms=500, sample_interval_ms=50
    )
    assert result["ok"] is True
    assert len(result["telemetry"]) >= 3
    await tool_output_off(config)

from unittest.mock import patch

import pytest

from psu_mcp.protocol import ProtocolHandle
from psu_mcp.session import AsyncProtocolHandle
from psu_mcp.telemetry import sample_until, Sample
from psu_mcp.vendors import KORAD_KA3005P


@pytest.fixture
def async_handle(fake_psu):
    return AsyncProtocolHandle(ProtocolHandle(fake_psu, KORAD_KA3005P))


class TestSampleUntil:
    async def test_returns_at_least_one_sample(self, async_handle, fake_psu):
        fake_psu.output_on = True
        fake_psu.vset_mv = 3300
        samples = await sample_until(async_handle, duration_ms=200, interval_ms=50)
        assert len(samples) >= 1

    async def test_samples_have_increasing_t_ms(self, async_handle, fake_psu):
        fake_psu.output_on = True
        samples = await sample_until(async_handle, duration_ms=300, interval_ms=50)
        ts = [s.t_ms for s in samples]
        assert ts == sorted(ts)
        assert ts[0] == 0

    async def test_samples_carry_vout_and_iout(self, async_handle, fake_psu):
        fake_psu.output_on = True
        fake_psu.vset_mv = 3300
        fake_psu.iset_ma = 50
        samples = await sample_until(async_handle, duration_ms=100, interval_ms=50)
        assert all(isinstance(s, Sample) for s in samples)
        assert all(s.vout_mv == 3300 for s in samples)
        assert all(s.iout_ma == 50 for s in samples)

    async def test_off_psu_reads_zero(self, async_handle, fake_psu):
        fake_psu.output_on = False
        samples = await sample_until(async_handle, duration_ms=100, interval_ms=50)
        assert all(s.vout_mv == 0 for s in samples)
        assert all(s.iout_ma == 0 for s in samples)

    async def test_interval_too_fast_is_clamped(self, async_handle, fake_psu):
        samples = await sample_until(async_handle, duration_ms=200, interval_ms=10)
        assert len(samples) <= 5

    async def test_zero_duration_returns_one_sample(self, async_handle, fake_psu):
        samples = await sample_until(async_handle, duration_ms=0, interval_ms=50)
        assert len(samples) == 1
        assert samples[0].t_ms == 0

from unittest.mock import patch

import pytest

from psu_mcp.session import psu_session
from psu_mcp.vendors import KORAD_KA3005P


class TestPSUSession:
    async def test_opens_and_closes_serial(self, fake_serial):
        with patch("psu_mcp.session._open_serial", return_value=fake_serial) as mock_open:
            async with psu_session("/dev/ttyACM0", KORAD_KA3005P) as handle:
                assert handle is not None
                handle.output_off()
            mock_open.assert_called_once_with("/dev/ttyACM0", KORAD_KA3005P)
        assert fake_serial.closed

    async def test_closes_on_exception(self, fake_serial):
        with patch("psu_mcp.session._open_serial", return_value=fake_serial):
            with pytest.raises(RuntimeError, match="boom"):
                async with psu_session("/dev/ttyACM0", KORAD_KA3005P):
                    raise RuntimeError("boom")
        assert fake_serial.closed

    async def test_handle_supports_protocol_calls(self, fake_serial):
        fake_serial.queue_response(b"03.30")
        with patch("psu_mcp.session._open_serial", return_value=fake_serial):
            async with psu_session("/dev/ttyACM0", KORAD_KA3005P) as handle:
                mv = await handle.read_vset_mv_async()
                assert mv == 3300

    async def test_handle_async_set_voltage(self, fake_serial):
        with patch("psu_mcp.session._open_serial", return_value=fake_serial):
            async with psu_session("/dev/ttyACM0", KORAD_KA3005P) as handle:
                await handle.set_voltage_v_async(3.30)
        assert fake_serial.tx_log == [b"VSET1:3.30"]

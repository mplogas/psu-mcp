import pytest

from psu_mcp.protocol import ProtocolHandle
from psu_mcp.vendors import KORAD_KA3005P


@pytest.fixture
def handle(fake_serial):
    return ProtocolHandle(fake_serial, KORAD_KA3005P)


class TestCommandEncoding:
    def test_set_voltage_writes_vset(self, handle, fake_serial):
        handle.set_voltage_v(3.30)
        assert fake_serial.tx_log == [b"VSET1:3.30"]

    def test_set_voltage_formats_two_decimals(self, handle, fake_serial):
        handle.set_voltage_v(5.0)
        assert fake_serial.tx_log == [b"VSET1:5.00"]

    def test_set_current_writes_iset(self, handle, fake_serial):
        handle.set_current_a(1.0)
        assert fake_serial.tx_log == [b"ISET1:1.000"]

    def test_set_current_three_decimals(self, handle, fake_serial):
        handle.set_current_a(0.5)
        assert fake_serial.tx_log == [b"ISET1:0.500"]

    def test_output_on(self, handle, fake_serial):
        handle.output_on()
        assert fake_serial.tx_log == [b"OUT1"]

    def test_output_off(self, handle, fake_serial):
        handle.output_off()
        assert fake_serial.tx_log == [b"OUT0"]

    def test_recall_profile(self, handle, fake_serial):
        handle.recall_profile(3)
        assert fake_serial.tx_log == [b"RCL3"]

    @pytest.mark.parametrize("slot", [0, 6, -1])
    def test_recall_profile_invalid_slot_raises(self, handle, slot):
        with pytest.raises(ValueError, match="slot"):
            handle.recall_profile(slot)


class TestQueryParsing:
    def test_read_vset_parses_voltage_string(self, handle, fake_serial):
        fake_serial.queue_response(b"03.30")
        result = handle.read_vset_mv()
        assert result == 3300
        assert fake_serial.tx_log == [b"VSET1?"]

    def test_read_iset_parses_current_string(self, handle, fake_serial):
        fake_serial.queue_response(b"1.000")
        result = handle.read_iset_ma()
        assert result == 1000

    def test_read_vout_parses(self, handle, fake_serial):
        fake_serial.queue_response(b"03.28")
        result = handle.read_vout_mv()
        assert result == 3280

    def test_read_iout_parses(self, handle, fake_serial):
        fake_serial.queue_response(b"0.042")
        result = handle.read_iout_ma()
        assert result == 42

    def test_read_status_returns_byte(self, handle, fake_serial):
        fake_serial.queue_response(b"\x41")
        status = handle.read_status_byte()
        assert status == 0x41

    def test_read_status_decodes_output_on(self, handle, fake_serial):
        fake_serial.queue_response(b"\x41")
        assert handle.read_output_on() is True

    def test_read_status_decodes_output_off(self, handle, fake_serial):
        fake_serial.queue_response(b"\x01")
        assert handle.read_output_on() is False


class TestErrorHandling:
    def test_empty_response_raises(self, handle, fake_serial):
        from psu_mcp.protocol import ProtocolError
        with pytest.raises(ProtocolError, match="no response"):
            handle.read_vset_mv()

    def test_unparseable_response_raises(self, handle, fake_serial):
        from psu_mcp.protocol import ProtocolError
        fake_serial.queue_response(b"NOT_A_NUMBER")
        with pytest.raises(ProtocolError, match="parse"):
            handle.read_vset_mv()

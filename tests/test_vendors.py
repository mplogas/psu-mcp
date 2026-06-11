# tests/test_vendors.py
import pytest

from psu_mcp.vendors import (
    VendorStrategy,
    get_vendor,
    list_vendors,
    KORAD_KA3005P,
)


class TestKoradKA3005P:
    def test_registered_under_canonical_name(self):
        v = get_vendor("korad_ka3005p")
        assert v.name == "korad_ka3005p"

    def test_baud_is_9600(self):
        v = get_vendor("korad_ka3005p")
        assert v.baud == 9600

    def test_voltage_command_template(self):
        v = get_vendor("korad_ka3005p")
        assert v.cmd_set_voltage.format(v=3.30) == "VSET1:3.30"

    def test_current_command_template(self):
        v = get_vendor("korad_ka3005p")
        assert v.cmd_set_current.format(a=1.000) == "ISET1:1.000"

    def test_output_on_and_off_commands(self):
        v = get_vendor("korad_ka3005p")
        assert v.cmd_output_on == "OUT1"
        assert v.cmd_output_off == "OUT0"

    def test_recall_command_template(self):
        v = get_vendor("korad_ka3005p")
        assert v.cmd_recall_profile.format(slot=2) == "RCL2"

    def test_read_commands_present(self):
        v = get_vendor("korad_ka3005p")
        assert v.cmd_read_vset == "VSET1?"
        assert v.cmd_read_iset == "ISET1?"
        assert v.cmd_read_vout == "VOUT1?"
        assert v.cmd_read_iout == "IOUT1?"
        assert v.cmd_read_status == "STATUS?"

    def test_profile_count_is_5(self):
        v = get_vendor("korad_ka3005p")
        assert v.profile_count == 5

    def test_decimals(self):
        v = get_vendor("korad_ka3005p")
        assert v.voltage_decimals == 2
        assert v.current_decimals == 3

    def test_no_response_terminator(self):
        v = get_vendor("korad_ka3005p")
        assert v.response_terminator == b""

    def test_strategy_is_frozen(self):
        v = get_vendor("korad_ka3005p")
        with pytest.raises(Exception):
            v.name = "modified"  # type: ignore[misc]


class TestRegistry:
    def test_unknown_vendor_raises(self):
        with pytest.raises(KeyError, match="Unknown vendor"):
            get_vendor("rigol_dp832")

    def test_list_vendors_includes_korad(self):
        names = {v.name for v in list_vendors()}
        assert "korad_ka3005p" in names

    def test_constant_export(self):
        assert KORAD_KA3005P.name == "korad_ka3005p"

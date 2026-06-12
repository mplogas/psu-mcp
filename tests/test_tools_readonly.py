import pytest

from psu_mcp.tools import (
    tool_connect,
    tool_list_profiles,
    tool_get_status,
)


class TestConnect:
    async def test_returns_vendor_and_settings(self, with_psu, psu_config):
        with_psu.vset_mv = 3300
        with_psu.iset_ma = 500
        with_psu.output_on = False

        result = await tool_connect(psu_config)

        assert result["ok"] is True
        assert result["vendor"] == "korad_ka3005p"
        assert result["port"] == "/dev/ttyACM0"
        assert result["vset_mv"] == 3300
        assert result["iset_ma"] == 500
        assert result["output_on"] is False

    async def test_verifies_profiles_match_declared(self, with_psu, psu_config):
        # FakePSU defaults all 5 slots to 3300mv. psu_config declares
        # slot 3 as 5000mv -- this is a mismatch the verification should catch.
        result = await tool_connect(psu_config)
        warnings = result.get("warnings", [])
        mismatches = [w for w in warnings if "profile" in w.lower()]
        assert any("3" in w for w in mismatches)

    async def test_skips_verification_when_output_on(self, with_psu, psu_config):
        with_psu.output_on = True
        result = await tool_connect(psu_config)
        warnings = result.get("warnings", [])
        assert any("profile_verification_skipped" in w for w in warnings)

    async def test_profiles_verified_when_output_off(self, with_psu, psu_config):
        with_psu.output_on = False
        with_psu.profiles = {1: 3300, 2: 3300, 3: 3300, 4: 3300, 5: 3300}
        result = await tool_connect(psu_config)
        warnings = result.get("warnings", [])
        assert not any("profile_verification_skipped" in w for w in warnings)


class TestListProfiles:
    async def test_returns_declared_profiles(self, psu_config):
        result = await tool_list_profiles(psu_config)
        assert result["ok"] is True
        assert result["profiles"][1] == {"mv": 3300, "label": "BK7231"}
        assert result["profiles"][3] == {"mv": 5000, "label": "ESP_via_USB"}


class TestGetStatus:
    async def test_returns_live_state(self, with_psu, psu_config):
        with_psu.output_on = True
        with_psu.vset_mv = 3300
        with_psu.iset_ma = 500
        result = await tool_get_status(psu_config)
        assert result["ok"] is True
        assert result["vset_mv"] == 3300
        assert result["iset_ma"] == 500
        assert result["output_on"] is True
        assert result["vout_mv"] == 3300
        assert result["iout_ma"] == 500
        assert result["vendor"] == "korad_ka3005p"
        # Declared profiles in the status payload instead of bounds.
        assert 1 in result["declared_profiles"]
        assert result["declared_profiles"][1]["mv"] == 3300

    async def test_warns_when_vset_unrecognized(self, with_psu, psu_config):
        with_psu.output_on = False
        with_psu.vset_mv = 6000  # not in any declared profile (3300, 5000)
        result = await tool_get_status(psu_config)
        warnings = result.get("warnings", [])
        assert any("does not match" in w for w in warnings)

    async def test_no_warning_when_vset_matches(self, with_psu, psu_config):
        with_psu.output_on = False
        with_psu.vset_mv = 3300  # in declared profiles
        result = await tool_get_status(psu_config)
        warnings = result.get("warnings", [])
        assert not any("does not match" in w for w in warnings)

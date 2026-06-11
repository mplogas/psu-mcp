import json
from pathlib import Path

import pytest

from psu_mcp.profiles import (
    Profile,
    PSUConfig,
    load_config,
    ConfigError,
)


def write_config(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "config.json"
    p.write_text(json.dumps(data))
    return p


class TestLoadConfig:
    def test_minimal_valid_config(self, tmp_path):
        p = write_config(tmp_path, {
            "port": "/dev/ttyACM0",
            "vendor": "korad_ka3005p",
            "max_voltage_mv": 5000,
            "max_current_ma": 1000,
        })
        c = load_config(p)
        assert c.port == "/dev/ttyACM0"
        assert c.vendor == "korad_ka3005p"
        assert c.max_voltage_mv == 5000
        assert c.max_current_ma == 1000
        assert c.profiles == {}

    def test_profiles_parsed(self, tmp_path):
        p = write_config(tmp_path, {
            "port": "/dev/ttyACM0",
            "vendor": "korad_ka3005p",
            "max_voltage_mv": 5000,
            "max_current_ma": 1000,
            "profiles": {
                "1": {"mv": 3300, "label": "BK7231"},
                "3": {"mv": 5000, "label": "ESP_via_USB"},
            },
        })
        c = load_config(p)
        assert c.profiles[1] == Profile(slot=1, mv=3300, label="BK7231")
        assert c.profiles[3] == Profile(slot=3, mv=5000, label="ESP_via_USB")
        assert 2 not in c.profiles
        assert 4 not in c.profiles

    def test_missing_max_voltage_raises(self, tmp_path):
        p = write_config(tmp_path, {
            "port": "/dev/ttyACM0",
            "vendor": "korad_ka3005p",
            "max_current_ma": 1000,
        })
        with pytest.raises(ConfigError, match="max_voltage_mv"):
            load_config(p)

    def test_missing_max_current_raises(self, tmp_path):
        p = write_config(tmp_path, {
            "port": "/dev/ttyACM0",
            "vendor": "korad_ka3005p",
            "max_voltage_mv": 5000,
        })
        with pytest.raises(ConfigError, match="max_current_ma"):
            load_config(p)

    def test_invalid_slot_key_raises(self, tmp_path):
        p = write_config(tmp_path, {
            "port": "/dev/ttyACM0",
            "vendor": "korad_ka3005p",
            "max_voltage_mv": 5000,
            "max_current_ma": 1000,
            "profiles": {"foo": {"mv": 3300, "label": "X"}},
        })
        with pytest.raises(ConfigError, match="slot"):
            load_config(p)

    def test_profile_missing_mv_raises(self, tmp_path):
        p = write_config(tmp_path, {
            "port": "/dev/ttyACM0",
            "vendor": "korad_ka3005p",
            "max_voltage_mv": 5000,
            "max_current_ma": 1000,
            "profiles": {"1": {"label": "BK7231"}},
        })
        with pytest.raises(ConfigError, match="mv"):
            load_config(p)

    def test_file_not_found_raises(self, tmp_path):
        with pytest.raises(ConfigError, match="not found"):
            load_config(tmp_path / "nope.json")

    def test_malformed_json_raises(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{ not valid json")
        with pytest.raises(ConfigError, match="parse"):
            load_config(p)

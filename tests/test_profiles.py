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


_MIN_PROFILES = {"1": {"mv": 3300, "label": "BK7231"}}


class TestLoadConfig:
    def test_minimal_valid_config(self, tmp_path):
        p = write_config(tmp_path, {
            "port": "/dev/ttyACM0",
            "vendor": "korad_ka3005p",
            "profiles": _MIN_PROFILES,
        })
        c = load_config(p)
        assert c.port == "/dev/ttyACM0"
        assert c.vendor == "korad_ka3005p"
        assert c.profiles == {
            1: Profile(slot=1, mv=3300, label="BK7231"),
        }

    def test_profiles_parsed(self, tmp_path):
        p = write_config(tmp_path, {
            "port": "/dev/ttyACM0",
            "vendor": "korad_ka3005p",
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

    def test_missing_profiles_raises(self, tmp_path):
        p = write_config(tmp_path, {
            "port": "/dev/ttyACM0",
            "vendor": "korad_ka3005p",
        })
        with pytest.raises(ConfigError, match="profiles"):
            load_config(p)

    def test_empty_profiles_raises(self, tmp_path):
        p = write_config(tmp_path, {
            "port": "/dev/ttyACM0",
            "vendor": "korad_ka3005p",
            "profiles": {},
        })
        with pytest.raises(ConfigError, match="at least one slot"):
            load_config(p)

    def test_missing_port_raises(self, tmp_path):
        p = write_config(tmp_path, {
            "vendor": "korad_ka3005p",
            "profiles": _MIN_PROFILES,
        })
        with pytest.raises(ConfigError, match="port"):
            load_config(p)

    def test_missing_vendor_raises(self, tmp_path):
        p = write_config(tmp_path, {
            "port": "/dev/ttyACM0",
            "profiles": _MIN_PROFILES,
        })
        with pytest.raises(ConfigError, match="vendor"):
            load_config(p)

    def test_invalid_slot_key_raises(self, tmp_path):
        p = write_config(tmp_path, {
            "port": "/dev/ttyACM0",
            "vendor": "korad_ka3005p",
            "profiles": {"foo": {"mv": 3300, "label": "X"}},
        })
        with pytest.raises(ConfigError, match="slot"):
            load_config(p)

    def test_profile_missing_mv_raises(self, tmp_path):
        p = write_config(tmp_path, {
            "port": "/dev/ttyACM0",
            "vendor": "korad_ka3005p",
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


class TestDeclaredMvs:
    def test_returns_set_of_mvs(self):
        c = PSUConfig(
            port="/dev/ttyACM0",
            vendor="korad_ka3005p",
            profiles={
                1: Profile(slot=1, mv=3300, label="a"),
                2: Profile(slot=2, mv=5000, label="b"),
                3: Profile(slot=3, mv=3300, label="c"),  # dedup
            },
        )
        assert c.declared_mvs() == {3300, 5000}

    def test_empty_when_no_profiles(self):
        c = PSUConfig(
            port="/dev/ttyACM0",
            vendor="korad_ka3005p",
            profiles={},
        )
        assert c.declared_mvs() == set()

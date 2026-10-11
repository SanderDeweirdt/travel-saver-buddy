from datetime import date

import pytest

from mmscan.config import ConfigError, load_config
from tests.conftest import ROOT


def test_default_config_loads():
    cfg = load_config(ROOT / "config.yaml")
    assert cfg.cabins == ["economy", "business"]
    assert cfg.mile_cost_eur_cents == 1.16
    assert cfg.warnings == []


def test_unknown_key_named(default_config_dict, write_config):
    default_config_dict["api"]["foo"] = 1
    with pytest.raises(ConfigError, match=r"api\.foo"):
        load_config(write_config(default_config_dict))


def test_bad_value_named(default_config_dict, write_config):
    default_config_dict["api"]["take"] = 5
    with pytest.raises(ConfigError, match=r"api\.take"):
        load_config(write_config(default_config_dict))


def test_bad_region(default_config_dict, write_config):
    default_config_dict["region_pairs"][0]["origin"] = "Europa"
    with pytest.raises(ConfigError, match=r"region_pairs\.0\.origin"):
        load_config(write_config(default_config_dict))


def test_missing_file_is_config_error(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.yaml")


def test_odd_airport_warns(default_config_dict, write_config):
    default_config_dict["watchlist"]["origins"].append("MUNICH")
    cfg = load_config(write_config(default_config_dict))
    assert any("MUNICH" in w for w in cfg.warnings)


def test_benchmark_matches_both_directions():
    cfg = load_config(ROOT / "config.yaml")
    there = cfg.benchmark_for("business", "MUC", "Europe", "SIN", "Asia")
    back = cfg.benchmark_for("business", "SIN", "Asia", "MUC", "Europe")
    assert there.name == back.name == "business_europe_southeast_asia"
    assert cfg.benchmark_for("economy", "MUC", "Europe", "NRT", "Asia") is None


def test_date_range():
    cfg = load_config(ROOT / "config.yaml")
    assert cfg.date_range(date(2026, 10, 11)) == (date(2026, 10, 11), date(2027, 9, 6))

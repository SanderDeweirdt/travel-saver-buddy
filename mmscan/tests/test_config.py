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
    assert cfg.date_range(date(2026, 10, 11)) == (date(2026, 10, 11), date(2027, 4, 9))


def test_amex_points_are_priced_through_the_transfer_ratio(default_config_dict):
    from mmscan.config import Config

    data = {
        **default_config_dict,
        "mr_point_value_eur_cents": 1.2,
        "programs": {
            "singapore": {"mr_per_mile": 1.5},  # 3 points = 2 miles
            "aeroplan": {"mile_cost_eur_cents": 1.4},
        },
    }
    cfg = Config.model_validate(data)
    assert cfg.mile_cents("singapore") == pytest.approx(1.8)
    assert cfg.mile_cents("aeroplan") == 1.4  # no ratio: its own cents per mile
    assert cfg.mile_cents(None) == cfg.mile_cost_eur_cents
    with pytest.raises(Exception, match="mr_point_value_eur_cents"):
        Config.model_validate({**data, "mr_point_value_eur_cents": None})


def test_saved_settings_apply_over_config_yaml(default_config_dict, write_config):
    from mmscan.config import load_config

    path = write_config(default_config_dict)
    cfg = load_config(
        path,
        {
            "mr_point_value_eur_cents": 0.5,
            "programs": {"singapore": {"mr_per_mile": 2.0}, "united": {"enabled": True}},
            "not_a_setting": 1,  # ignored: only the settings page's keys count
        },
    )
    assert cfg.mile_cents("singapore") == pytest.approx(1.0)
    assert cfg.is_bookable("united") and not cfg.is_bookable("flyingblue")
    assert cfg.programs["singapore"].label == "KrisFlyer"  # merged per field, label kept
    assert load_config(path, {}).mr_point_value_eur_cents == 1.0  # nothing saved: config.yaml


def test_settings_saved_as_a_bookable_list_still_apply(default_config_dict, write_config):
    from mmscan.config import load_config

    cfg = load_config(
        write_config(default_config_dict), {"bookable_programs": ["lufthansa", "united"]}
    )
    assert cfg.is_bookable("united") and not cfg.is_bookable("singapore")

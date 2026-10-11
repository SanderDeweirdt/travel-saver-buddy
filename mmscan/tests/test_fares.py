import pytest

from mmscan.fares import CsvFareSource, value_band
from mmscan.scoring import score_rows
from tests.helpers import config, scored


def write(tmp_path, text):
    p = tmp_path / "cash_fares.csv"
    p.write_text(text)
    return p


def test_matching_row_fills_cash_columns(tmp_path, default_config_dict):
    fares = CsvFareSource(
        write(tmp_path, "origin,destination,cabin,month,fare_eur\nMUC,SIN,business,2026-12,1500\n")
    )
    cfg = config(default_config_dict)
    s = scored(746.0, miles=60000, fees=50)
    score_rows([s], [], cfg, fares)
    assert s.cash_fare_eur == 1500
    assert s.saving_eur == 754.0
    assert s.value_cents == pytest.approx(2.41666, rel=1e-4)
    assert s.value_band == "good"


def test_no_matching_row_leaves_blank_and_verdict_unchanged(tmp_path, default_config_dict):
    cfg = config(default_config_dict)
    with_fares, without = scored(746.0), scored(746.0)
    fares = CsvFareSource(
        write(tmp_path, "origin,destination,cabin,month,fare_eur\nFRA,SIN,business,2026-12,1500\n")
    )
    score_rows([with_fares], [], cfg, fares)
    score_rows([without], [], cfg)
    assert with_fares.cash_fare_eur is None and with_fares.value_band is None
    assert with_fares.verdict == without.verdict


def test_missing_file_gives_no_fares(tmp_path):
    fares = CsvFareSource(tmp_path / "nope.csv")
    assert fares.fare("MUC", "SIN", "business", "2026-12") is None
    assert fares.warnings == []


def test_bad_rows_skipped_with_line_numbers(tmp_path):
    fares = CsvFareSource(
        write(
            tmp_path,
            "origin,destination,cabin,month,fare_eur\n"
            "MUC,SIN,business,12/2026,1500\n"
            "MUC,SIN,business,2026-12,abc\n"
            "muc,sin,Business,2026-12,1400\n",
        )
    )
    assert len(fares.warnings) == 2
    assert "line 2" in fares.warnings[0] and "line 3" in fares.warnings[1]
    assert fares.fare("MUC", "SIN", "business", "2026-12") == 1400


def test_value_bands(default_config_dict):
    cfg = config(default_config_dict)
    assert value_band(2.0, cfg) == "good"
    assert value_band(1.5, cfg) == "fair"
    assert value_band(1.49, cfg) == "poor"
    assert value_band(None, cfg) is None

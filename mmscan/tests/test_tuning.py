"""Scoring knobs: relative.min_discount_pct and shortlist.scope / focus_watchlist."""

import pytest

from mmscan.report import shortlist
from mmscan.scoring import DEAL, WORTH, score_rows
from tests.helpers import config, scored


def cfg_with(default_config_dict, **kw):
    rel = {"percentile_good": 20, "min_samples": 5, "history_days": 30}
    rel.update(kw.pop("relative", {}))
    return config(default_config_dict, relative=rel, **kw)


def flat_route(price=700.0, n=8, **kw):
    return [scored(price, date=f"2026-12-{i + 1:02d}", **kw) for i in range(n)]


def test_flat_route_has_no_deals_with_a_discount(default_config_dict):
    rows = flat_route()
    score_rows(rows, [], cfg_with(default_config_dict, relative={"min_discount_pct": 10}))
    assert all(r.route_good is False and r.destination_good is False for r in rows)


def test_discount_zero_restores_the_plain_percentile_cut(default_config_dict):
    rows = flat_route()
    score_rows(rows, [], cfg_with(default_config_dict, relative={"min_discount_pct": 0}))
    assert all(r.verdict == DEAL for r in rows)


@pytest.mark.parametrize(("pct", "expected"), [(10, True), (30, False)])
def test_discount_threshold_is_against_the_median(default_config_dict, pct, expected):
    # Totals 80, 100 x7: median 100, p20 = 100 - nothing but the 80 can clear 10% below.
    cheap = scored(80.0, date="2026-12-01")
    rows = [cheap] + [scored(100.0, date=f"2026-12-{i + 2:02d}") for i in range(7)]
    score_rows(rows, [], cfg_with(default_config_dict, relative={"min_discount_pct": pct}))
    assert cheap.route_good is expected


def test_discount_must_be_below_100(default_config_dict):
    with pytest.raises(ValueError, match="min_discount_pct"):
        cfg_with(default_config_dict, relative={"min_discount_pct": 100})


def _deal(**kw):
    s = scored(700.0, **kw)
    s.verdict = DEAL
    return s


def test_focus_scope_keeps_benchmark_and_watchlist_only(default_config_dict):
    sea = _deal(origin="MUC", dest="SIN", id="a")  # benchmark: Europe <-> southeast_asia
    gulf = _deal(origin="MUC", dest="NRT", id="b")  # Asia, but no benchmark, not on the watchlist
    cfg = config(default_config_dict)
    assert [s.availability_id for s in shortlist([sea, gulf], cfg)] == ["a"]
    cfg_all = config(default_config_dict, shortlist={"scope": "all"})
    assert [s.availability_id for s in shortlist([sea, gulf], cfg_all)] == ["a", "b"]
    assert [s.availability_id for s in shortlist([sea, gulf])] == ["a", "b"]  # no cfg: no filter


def test_watchlist_pair_is_in_focus_even_without_a_benchmark(default_config_dict):
    wl_only = {"origins": ["MUC"], "destinations": ["NRT"], "both_directions": True}
    pair = _deal(origin="MUC", dest="NRT", id="a")
    back = _deal(origin="NRT", dest="MUC", id="b")
    other = _deal(origin="FRA", dest="NRT", id="c")
    cfg = config(default_config_dict, watchlist=wl_only)
    assert [s.availability_id for s in shortlist([pair, back, other], cfg)] == ["a", "b"]
    off = config(default_config_dict, watchlist=wl_only, shortlist={"focus_watchlist": False})
    assert shortlist([pair, back, other], off) == []


def test_worth_a_look_rows_follow_the_same_scope(default_config_dict):
    s = scored(700.0, origin="MUC", dest="NRT")
    s.verdict = WORTH
    assert shortlist([s], config(default_config_dict)) == []

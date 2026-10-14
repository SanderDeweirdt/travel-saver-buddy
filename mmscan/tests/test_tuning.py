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


# --- Deals by absolute price, and alerts on price drops --------------------------------------


def test_ceiling_makes_a_deal_on_a_flat_route(default_config_dict):
    rows = flat_route(
        price=700.0, miles=50000, fees=100.0
    )  # business chart saver 100,000 mi / 450 EUR
    cfg = cfg_with(
        default_config_dict, relative={"min_discount_pct": 10}, deals={"by_ceiling": True}
    )
    score_rows(rows, [], cfg)
    assert all(r.verdict == DEAL and r.route_good is False for r in rows)


def test_ceiling_deal_can_be_switched_off(default_config_dict):
    rows = flat_route(price=700.0, miles=50000, fees=100.0)
    cfg = cfg_with(
        default_config_dict, relative={"min_discount_pct": 10}, deals={"by_ceiling": False}
    )
    score_rows(rows, [], cfg)
    assert all(r.verdict != DEAL for r in rows)


def test_ceiling_deal_needs_seats_and_both_limits(default_config_dict):
    cfg = cfg_with(
        default_config_dict, relative={"min_discount_pct": 10}, deals={"by_ceiling": True}
    )
    no_seats = scored(700.0, miles=50000, fees=100.0, seats_ok=False, date="2026-12-01")
    high_fee = scored(700.0, miles=50000, fees=451.0, date="2026-12-02")
    high_miles = scored(700.0, miles=100001, fees=100.0, date="2026-12-03")
    score_rows([no_seats, high_fee, high_miles], [], cfg)
    assert [r.verdict == DEAL for r in (no_seats, high_fee, high_miles)] == [False] * 3


def test_drop_threshold_comes_from_config(default_config_dict):
    from mmscan.diff import change, change_for

    assert change(1000, 960, drop_pct=5) == ""
    assert change(1000, 960, drop_pct=4) == "Cheaper"
    prev = {("MUC", "SIN", "2026-12-10", "business"): 1000.0}
    key = ("MUC", "SIN", "2026-12-10", "business")
    assert change_for(prev, key, 900.0, 15) == ""
    assert change_for(prev, key, 900.0, 10) == "Cheaper"
    with pytest.raises(ValueError, match="min_pct"):
        config(default_config_dict, drops={"min_pct": 0})


def _alert_row(change, verdict, **kw):
    s = scored(700.0, **kw)
    s.change, s.verdict = change, verdict
    return s


def test_on_drop_alerts_cheaper_results_of_any_verdict(default_config_dict):
    from mmscan.notify import build_message, select_alerts

    cheaper_skip = _alert_row("Cheaper", "Skip", id="a")
    new_skip = _alert_row("New", "Skip", id="b")
    new_deal = _alert_row("New", DEAL, id="c")
    quiet_deal = _alert_row("", DEAL, id="d")
    off_scope = _alert_row("Cheaper", "Skip", origin="MUC", dest="NRT", id="e")
    rows = [cheaper_skip, new_skip, new_deal, quiet_deal, off_scope]
    cfg = config(default_config_dict)
    assert [s.availability_id for s in select_alerts(rows, cfg)] == ["c", "a"]
    off = config(default_config_dict, notify={"on_drop": False})
    assert [s.availability_id for s in select_alerts(rows, off)] == ["c"]
    from datetime import UTC, datetime

    text = build_message([cheaper_skip], 1, cfg, datetime(2026, 10, 12, tzinfo=UTC))["blocks"][1][
        "text"
    ]["text"]
    assert text.startswith("*Cheaper* ·")

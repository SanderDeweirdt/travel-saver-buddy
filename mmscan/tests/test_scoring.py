from datetime import UTC, datetime, timedelta

import pytest

from mmscan.scoring import (
    DEAL,
    SKIP,
    WORTH,
    pick_trip,
    rank_key,
    score_rows,
    score_run,
    total_cost_eur,
    verdict,
)
from mmscan.store import Store
from tests.helpers import avail, config, scored, trip

NOW = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)


@pytest.fixture
def cfg(default_config_dict):
    # min_samples 5 keeps the samples small; percentile_good stays 20.
    return config(
        default_config_dict, relative={"percentile_good": 20, "min_samples": 5, "history_days": 30}
    )


def route(totals, origin="MUC", dest="SIN", cabin="business"):
    return [
        scored(t, origin=origin, dest=dest, cabin=cabin, date=f"2026-12-{i + 1:02d}")
        for i, t in enumerate(totals)
    ]


def test_total_cost_example():
    assert total_cost_eur(42500, 50, 1.16) == 543.0


def test_pick_trip_prefers_seats():
    trips = [trip("cheap", taxes=1000, seats=1), trip("ok", taxes=5000, seats=2)]
    t, seats_ok = pick_trip(trips, "business", 2, 1.16)
    assert (t.id, seats_ok) == ("ok", True)


def test_pick_trip_unknown_seats_count_as_meeting():
    t, seats_ok = pick_trip([trip("u", seats=None)], "business", 2, 1.16)
    assert seats_ok is True


def test_pick_trip_falls_back_and_flags_seats():
    trips = [trip("a", taxes=1000, seats=1), trip("b", taxes=5000, seats=1)]
    t, seats_ok = pick_trip(trips, "business", 2, 1.16)
    assert (t.id, seats_ok) == ("a", False)


def test_pick_trip_ignores_other_cabin_and_non_eur():
    trips = [trip("e", cabin="economy"), trip("usd", currency="USD")]
    assert pick_trip(trips, "business", 2, 1.16) is None


def test_route_good_at_20th_percentile_inclusive(cfg):
    rows = route([100, 200, 300, 400, 500, 600])  # p20 = 200
    score_rows(rows, [], cfg)
    by_total = {r.total_eur: r for r in rows}
    assert by_total[200].route_good is True
    assert by_total[300].route_good is False


def test_destination_baseline_groups_by_origin_region(cfg):
    rows = route([1000, 1000, 1000], origin="MUC") + route([100, 100, 100], origin="FRA")
    score_rows(rows, [], cfg)
    # Six samples across Europe->SIN; p20 is 100, so MUC rows are not destination-good.
    muc = [r for r in rows if r.origin == "MUC"]
    fra = [r for r in rows if r.origin == "FRA"]
    assert all(r.destination_good is False for r in muc)
    assert all(r.destination_good is True for r in fra)


def test_ceiling_good_needs_miles_and_fees(cfg):
    ok, high_fee, high_miles = (
        scored(800, miles=60000, fees=450),
        scored(900, miles=60000, fees=451, date="2026-12-02"),
        scored(900, miles=60001, fees=50, date="2026-12-03"),
    )
    score_rows([ok, high_fee, high_miles], [], cfg)
    assert (ok.ceiling_good, high_fee.ceiling_good, high_miles.ceiling_good) == (True, False, False)


def test_chart_rate_at_95_percent(cfg):
    at, below = scored(1200, miles=95000), scored(1200, miles=94999, date="2026-12-02")
    score_rows([at, below], [], cfg)
    assert at.chart_rate is True and below.chart_rate is False


def test_estimated_fee_in_baseline_not_shortlisted(cfg):
    priced = route([700, 750, 800, 850])
    est = scored(None, miles=40000, fees=None, estimated=True, date="2026-12-20")
    score_rows(priced + [est], [], cfg)
    # Median actual fee is 50, so the estimate is 40000 x 1.16 ct + 50.
    assert est.fees_eur == 50 and est.total_eur == 514.0
    assert est.route_good is True  # it counted: 5 samples now meet min_samples
    from mmscan.report import shortlist

    assert est not in shortlist(priced + [est])


def test_route_without_priced_result_excluded(cfg):
    est = scored(None, origin="FRA", fees=None, estimated=True)
    others = route([100, 200, 300, 400, 500])
    score_rows(others + [est], [], cfg)
    assert est.total_eur is None and est.verdict == SKIP
    # The destination baseline is the five MUC rows only.
    assert others[0].destination_pct == 10.0


def test_thin_data_uses_ceiling(cfg):
    good = scored(500, miles=50000, fees=100)
    bad = scored(900, miles=70000, fees=100, date="2026-12-02")
    score_rows([good, bad], [], cfg)
    assert (good.route_good, good.destination_good, good.verdict) == (True, True, DEAL)
    assert bad.verdict == SKIP


def test_thin_data_no_benchmark_caps_at_worth_a_look(cfg):
    # MUC-NRT matches no benchmark (Southeast Asia only). Route is thin; destination too.
    rows = route([100, 200, 300], dest="NRT")
    score_rows(rows, [], cfg)
    assert all(r.verdict == SKIP for r in rows)
    # With a full destination baseline but a thin route, the best is Worth a look.
    many = route([100, 200, 300, 400, 500, 600], dest="NRT", origin="FRA")
    one = route([90], dest="NRT", origin="ZRH")
    score_rows(many + one, [], cfg)
    assert one[0].destination_good is True and one[0].route_good is False
    assert one[0].verdict == WORTH


def test_verdict_table():
    assert verdict(True, True, True) == DEAL
    assert verdict(True, False, True) == WORTH
    assert verdict(False, True, False) == WORTH
    assert verdict(True, True, False) == WORTH  # builder call 5
    assert verdict(True, True, True, capped=True) == WORTH
    assert verdict(False, False, True) == SKIP


def test_history_window_and_dedupe(tmp_path, cfg):
    store = Store(tmp_path / "db.sqlite")
    old = store.start_run("scan", "{}", now=NOW - timedelta(days=40))
    recent = store.start_run("scan", "{}", now=NOW - timedelta(days=2))
    current = store.start_run("scan", "{}", now=NOW)
    store.save_availability(old, avail("o1", business=60000), "region")
    store.save_availability(recent, avail("r1", business=60000), "region")
    store.save_availability(current, avail("c1", business=60000), "region")
    for avail_id in ("o1", "r1", "c1"):
        store.save_trips(
            avail_id, "2026-10-10T08:00:00Z", [trip(f"t{avail_id}", avail_id=avail_id)], None, {}
        )
    for run in (old, recent):
        score_run(store, cfg, run, NOW)
    from mmscan.scoring import history_rows

    hist = history_rows(store, cfg, current, NOW)
    assert {h.availability_id for h in hist} == {"r1"}  # o1 is outside history_days
    rows, _ = score_run(store, cfg, current, NOW)
    # r1 and c1 share route, date and cabin, so only c1 counts: 1 sample, thin.
    assert rows[0].route_pct == 50.0


def test_ranking_direct_wins_ties():
    a = scored(500, direct=False, id="a")
    b = scored(500, direct=True, id="b")
    c = scored(400, direct=False, id="c")
    for s in (a, b, c):
        s.verdict = WORTH
    a.verdict = DEAL
    assert [s.availability_id for s in sorted([a, b, c], key=rank_key)] == ["a", "c", "b"]
    a.verdict = WORTH
    assert [s.availability_id for s in sorted([a, b, c], key=rank_key)] == ["c", "b", "a"]


def test_empty_run_scores_nothing(tmp_path, cfg):
    store = Store(tmp_path / "db.sqlite")
    run = store.start_run("scan", "{}", now=NOW)
    rows, warnings = score_run(store, cfg, run, NOW)
    assert rows == [] and warnings == []


def test_score_run_prices_from_stored_trips(tmp_path, cfg):
    store = Store(tmp_path / "db.sqlite")
    run = store.start_run("scan", "{}", now=NOW)
    store.save_availability(run, avail("a", business=60000, economy=35000), "region")
    store.save_trips(
        "a",
        "2026-10-10T08:00:00Z",
        [
            trip("tj", taxes=39850),
            trip("ty", cabin="economy", miles=35000, taxes=12900, currency=""),
        ],
        "https://example.test/book",
        {},
    )
    rows, warnings = score_run(store, cfg, run, NOW)
    by_cabin = {r.cabin: r for r in rows}
    assert by_cabin["business"].total_eur == total_cost_eur(60000, 398.50, 1.16)
    assert by_cabin["economy"].fees_eur == 129.0
    assert by_cabin["business"].booking_link == "https://example.test/book"
    assert any("empty TaxesCurrency" in w for w in warnings)
    stored = store.conn.execute("SELECT count(*) FROM results WHERE run_id=?", (run,)).fetchone()[0]
    assert stored == 2

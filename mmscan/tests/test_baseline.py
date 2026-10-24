from datetime import UTC, datetime, timedelta

from mmscan.baseline import (
    baseline_for,
    build_baselines,
    price_group,
    route_baselines,
    thin_routes,
)
from mmscan.scoring import score_run
from mmscan.store import Store
from tests.helpers import avail, config, scored, trip


def cfg(default_config_dict, n=3, **kw):
    return config(default_config_dict, relative={"percentile_good": 20, "min_samples": n}, **kw)


def test_median_and_sample_count(default_config_dict):
    c = cfg(default_config_dict)
    rows = [scored(t, date=f"2026-12-{d:02d}") for d, t in ((1, 900), (2, 1000), (3, 1200))]
    b = build_baselines(rows, c)[("MUC", "SIN", "business", "fixed", None)]
    assert (b.median, b.n, b.ready) == (1000, 3, True)


def test_thin_route_has_no_baseline(default_config_dict):
    c = cfg(default_config_dict)
    rows = [scored(900, date="2026-12-01"), scored(1000, date="2026-12-02")]
    baselines = build_baselines(rows, c)
    assert baseline_for(baselines, c, rows[0]) is None
    assert thin_routes(baselines) == 1


def test_fixed_and_dynamic_do_not_share_a_baseline(default_config_dict):
    c = cfg(default_config_dict, n=2)
    fixed = [scored(800, date=f"2026-12-0{d}", carriers="SQ") for d in (1, 2)]
    dynamic = [scored(1600, date=f"2026-12-1{d}", carriers="LH") for d in (1, 2)]
    baselines = build_baselines(fixed + dynamic, c)
    assert baseline_for(baselines, c, fixed[0]).median == 800
    assert baseline_for(baselines, c, dynamic[0]).median == 1600
    assert price_group(c, "LH, SQ") == "dynamic"  # mixed counts as dynamic
    assert price_group(c, None) == "dynamic"


def test_latest_observation_wins_and_expired_is_ignored(default_config_dict):
    c = cfg(default_config_dict, n=1)
    old, new = scored(1000, id="x"), scored(700, id="x")
    gone = scored(5000, date="2026-12-09")
    gone.expired = True
    b = build_baselines([old, new, gone], c)[("MUC", "SIN", "business", "fixed", None)]
    assert (b.median, b.n) == (700, 1)


def test_cabins_and_routes_are_separate(default_config_dict):
    c = cfg(default_config_dict, n=1)
    rows = [scored(900), scored(400, cabin="economy"), scored(950, origin="FRA")]
    assert len(build_baselines(rows, c)) == 3


def test_route_baselines_from_the_store(tmp_path, default_config_dict):
    c = cfg(default_config_dict, n=2)
    store = Store(tmp_path / "b.db")
    now = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)
    for days, miles in ((2, 70000), (1, 64000), (0, 58000)):
        at = now - timedelta(days=days)
        run = store.start_run("watch", "{}", now=at)
        store.save_availability(
            run, avail(f"a{days}", date=f"2026-12-1{days}", business=miles), "watchlist"
        )
        store.save_trips(
            f"a{days}",
            "2026-10-10T08:00:00Z",
            [trip(f"t{days}", avail_id=f"a{days}", miles=miles, taxes=30000)],
            "x",
            {},
        )
        score_run(store, c, run, at)
        store.finish_run(run, "ok", {}, [], now=at)
    b = route_baselines(store, c)[("MUC", "SIN", "business", "fixed", "lufthansa")]
    assert b.ready and b.n == 3  # three flight dates
    store.close()

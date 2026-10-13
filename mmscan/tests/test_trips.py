from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import ValidationError

from mmscan.config import ConfigError, load_config
from mmscan.notify import build_message, notify_run
from mmscan.scan import trip_requests, watchlist_requests
from mmscan.scoring import score_run
from mmscan.store import Store
from mmscan.trips import build_trip, latest_legs, trip_alerts, trip_views
from tests.helpers import avail, config

NOW = datetime.now(UTC)
TRIP = {
    "name": "Family stay",
    "origins": ["MUC"],
    "destinations": ["SIN"],
    "depart": {"start": date(2027, 6, 1), "end": date(2027, 6, 20)},
    "return": {"start": date(2027, 8, 15), "end": date(2027, 8, 31)},
    "cabins": ["business"],
    "seats": 2,
}


def cfg_with(d, **trip_overrides):
    return config(d, trips=[{**TRIP, **trip_overrides}])


def add_run(store, cfg, legs, at=None, kind="watch"):
    """legs: (id, origin, dest, date, miles, taxes_usd_minor, seats)."""
    at = at or NOW
    run = store.start_run(kind, "{}", now=at)
    for id, o, d, day, miles, tax, seats in legs:
        a = avail(id, origin=o, dest=d, date=day, taxes={"business": tax}, business=miles)
        a["JRemainingSeats"] = seats
        store.save_availability(run, a, "watchlist")
    score_run(store, cfg, run, at)
    store.finish_run(run, "ok", {}, [], now=at)
    return run


LEGS = [
    ("o1", "MUC", "SIN", "2027-06-10", 60000, 30000, 4),
    ("o2", "MUC", "SIN", "2027-06-12", 70000, 30000, 4),
    ("o3", "MUC", "SIN", "2027-07-30", 40000, 30000, 4),  # outside the departure window
    ("b1", "SIN", "MUC", "2027-08-20", 60000, 30000, 4),
    ("b2", "SIN", "MUC", "2027-08-25", 50000, 30000, 4),
    ("b3", "SIN", "MUC", "2027-06-05", 30000, 30000, 4),  # before the return window
]


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "t.db")
    yield s
    s.close()


def test_config_parses_trip_and_defaults(default_config_dict):
    cfg = cfg_with(default_config_dict)
    t = cfg.trips[0]
    assert t.return_window.start == date(2027, 8, 15)
    assert cfg.trip_seats(t) == 2 and cfg.trip_cabins(t) == ["business"]
    no_overrides = {k: v for k, v in TRIP.items() if k not in ("cabins", "seats")}
    t2 = config(default_config_dict, trips=[no_overrides]).trips[0]
    assert cfg.trip_cabins(t2) == cfg.cabins


def test_config_rejects_bad_trips(default_config_dict, write_config):
    bad = [
        {**TRIP, "return": None, "stay_days": {"min": 5, "max": 9}},
        {**TRIP, "stay_days": {"min": 9, "max": 5}},
        {**TRIP, "depart": {"start": date(2027, 6, 20), "end": date(2027, 6, 1)}},
        {**TRIP, "origins": []},
    ]
    for trip in bad:
        with pytest.raises(ValidationError):
            config(default_config_dict, trips=[trip])
    with pytest.raises(ValidationError, match="unique"):
        config(default_config_dict, trips=[TRIP, TRIP])
    path = write_config({**default_config_dict, "trips": [{**TRIP, "bogus": 1}]})
    with pytest.raises(ConfigError):
        load_config(path)


def test_trip_requests_are_narrow_and_skip_past_windows(default_config_dict):
    cfg = cfg_with(default_config_dict)
    reqs = trip_requests(cfg, date(2027, 1, 1))
    assert len(reqs) == 2
    (_, out), (_, back) = reqs
    assert (out["origin_airport"], out["destination_airport"]) == ("MUC", "SIN")
    assert (out["start_date"], out["end_date"]) == ("2027-06-01", "2027-06-20")
    assert (back["origin_airport"], back["destination_airport"]) == ("SIN", "MUC")
    assert back["cabins"] == "business" and back["include_trips"] is True
    # Once the departure window has started, the scan starts today.
    assert trip_requests(cfg, date(2027, 6, 5))[0][1]["start_date"] == "2027-06-05"
    # A window in the past is not scanned.
    assert len(trip_requests(cfg, date(2027, 6, 25))) == 1
    assert len(watchlist_requests(cfg, date(2027, 1, 1))) == 2 + 2  # wide watchlist + trip legs


def test_pairs_respect_windows_and_rank_by_party_total(default_config_dict, store):
    cfg = cfg_with(default_config_dict)
    add_run(store, cfg, LEGS)
    (view,) = trip_views(store, cfg, NOW)
    assert (view.n_out, view.n_back) == (2, 2)
    assert view.n_pairs == 4
    best = view.best
    assert (best.out.date, best.back.date) == ("2027-06-10", "2027-08-25")
    assert best.party_total == pytest.approx(best.total_pp * 2)
    assert best.miles_pp == 110000
    assert best.stay_days == 76
    assert [p.party_total for p in view.pairs] == sorted(p.party_total for p in view.pairs)


def test_stay_days_budget_and_stops(default_config_dict, store):
    legs = latest_legs(store, cfg_with(default_config_dict), NOW)
    assert legs == []
    cfg = cfg_with(default_config_dict)
    add_run(store, cfg, LEGS)
    legs = latest_legs(store, cfg, NOW)
    stay = cfg_with(default_config_dict, stay_days={"min": 70, "max": 75})
    pairs = build_trip(legs, stay.trips[0], stay).pairs
    assert {(p.out.date, p.back.date) for p in pairs} == {
        ("2027-06-10", "2027-08-20"),
        ("2027-06-12", "2027-08-25"),
    }
    budget = cfg_with(default_config_dict, max_total_eur=3800)
    v = build_trip(legs, budget.trips[0], budget)
    assert 0 < v.n_within_budget < v.n_pairs
    assert v.best.within_budget is True
    one_way = cfg_with(default_config_dict, **{"return": None})
    assert build_trip(legs, one_way.trips[0], one_way).n_pairs == 2


def test_not_enough_seats_and_empty_note(default_config_dict, store):
    cfg = cfg_with(default_config_dict, seats=3)
    add_run(store, cfg, [(i, o, d, day, m, t, 2) for i, o, d, day, m, t, _ in LEGS])
    (view,) = trip_views(store, cfg, NOW)
    assert view.pairs == [] and "No outbound" in view.note


def test_open_jaw_needs_the_flag(default_config_dict, store):
    legs = [
        ("o1", "MUC", "SIN", "2027-06-10", 60000, 30000, 4),
        ("b1", "SIN", "FRA", "2027-08-20", 60000, 30000, 4),
    ]
    base = dict(origins=["MUC", "FRA"], destinations=["SIN"])
    plain = cfg_with(default_config_dict, **base)
    add_run(store, plain, legs)
    legs_now = latest_legs(store, plain, NOW)
    assert build_trip(legs_now, plain.trips[0], plain).n_pairs == 0
    jaw = cfg_with(default_config_dict, open_jaw=True, **base)
    assert build_trip(legs_now, jaw.trips[0], jaw).n_pairs == 1


def test_alerts_new_cheaper_and_first_run_silent(default_config_dict, store):
    cfg = cfg_with(default_config_dict, alert_top=1)
    t0 = NOW - timedelta(hours=2)
    first = add_run(store, cfg, LEGS, at=t0)
    assert trip_alerts(store, cfg, first, t0) == []  # nothing to compare with
    cheaper = [
        (i, o, d, day, int(m * 0.8) if i == "o1" else m, t, s) for i, o, d, day, m, t, s in LEGS
    ]
    second = add_run(store, cfg, cheaper, at=NOW)
    (alert,) = trip_alerts(store, cfg, second, NOW)
    assert alert.change == "Cheaper" and alert.was > alert.pair.party_total
    assert alert.pair.out.availability_id == "o1"
    # Unchanged prices alert nothing.
    third = add_run(store, cfg, cheaper, at=NOW + timedelta(minutes=5))
    assert trip_alerts(store, cfg, third, NOW + timedelta(minutes=5)) == []
    # A cheaper return that creates a new best pair is New.
    fourth_legs = cheaper + [("b9", "SIN", "MUC", "2027-08-22", 20000, 30000, 4)]
    at = NOW + timedelta(minutes=10)
    fourth = add_run(store, cfg, fourth_legs, at=at)
    (alert,) = trip_alerts(store, cfg, fourth, at)
    assert alert.change == "New" and alert.pair.back.availability_id == "b9"


def test_message_and_notify_run_include_trips(default_config_dict, store):
    cfg = cfg_with(default_config_dict, alert_top=1)
    t0 = NOW - timedelta(hours=2)
    add_run(store, cfg, LEGS, at=t0)
    cheaper = [
        (i, o, d, day, int(m * 0.7) if i == "b2" else m, t, s) for i, o, d, day, m, t, s in LEGS
    ]
    run = add_run(store, cfg, cheaper, at=NOW)
    n, payload = notify_run(store, cfg, run, NOW, None)
    assert n >= 1
    text = " ".join(b["text"]["text"] for b in payload["blocks"] if b["type"] == "section")
    assert "Family stay" in text and "2 travellers" in text and "Cheaper (was" in text
    alerts = trip_alerts(store, cfg, run, NOW)
    msg = build_message([], run, cfg, NOW, alerts)
    assert msg["text"] == "mmscan: 1 new or cheaper award"

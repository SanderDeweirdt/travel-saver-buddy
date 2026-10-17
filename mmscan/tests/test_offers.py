"""Observations and current offers: one latest price per flight, compared with the usual price."""

from datetime import UTC, datetime, timedelta

import pytest

from mmscan.offers import load_current, record_observations
from mmscan.scoring import current_rows, score_run
from mmscan.store import Store
from tests.helpers import avail, config

NOW = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)


@pytest.fixture
def cfg(default_config_dict):
    return config(default_config_dict, relative={"min_samples": 3, "history_days": 30})


def _scan(store, cfg, at, flights, kind="watch"):
    """One run: `flights` is a list of (id, date, miles, taxes_usd_minor)."""
    run = store.start_run(kind, "{}", now=at)
    for id_, date, miles, taxes in flights:
        store.save_availability(
            run,
            avail(id_, date=date, taxes={"economy": taxes}, economy=miles, airlines="SQ"),
            "watchlist",
        )
    score_run(store, cfg, run, at)
    return run


def _obs(store):
    return store.conn.execute("SELECT * FROM observations ORDER BY id").fetchall()


def test_unchanged_rescan_bumps_last_seen_without_a_new_row(tmp_path, cfg):
    store = Store(tmp_path / "db.sqlite")
    _scan(store, cfg, NOW, [("a", "2026-12-10", 35000, 12900)])
    later = NOW + timedelta(hours=1)
    _scan(store, cfg, later, [("a", "2026-12-10", 35000, 12900)])
    (row,) = _obs(store)
    assert row["first_seen"] == NOW.isoformat() and row["last_seen"] == later.isoformat()


def test_changed_price_adds_a_row_and_keeps_history(tmp_path, cfg):
    store = Store(tmp_path / "db.sqlite")
    _scan(store, cfg, NOW, [("a", "2026-12-10", 35000, 12900)])
    _scan(store, cfg, NOW + timedelta(hours=1), [("a", "2026-12-10", 30000, 12900)])
    rows = _obs(store)
    assert [r["miles"] for r in rows] == [35000, 30000]
    (cur,) = load_current(store)
    assert cur.miles == 30000 and cur.change == "Cheaper"


def test_same_run_scored_twice_replaces_its_own_row(tmp_path, cfg):
    store = Store(tmp_path / "db.sqlite")
    run = store.start_run("run", "{}", now=NOW)
    store.save_availability(run, avail("a", taxes={"economy": 12900}, economy=35000), "region")
    score_run(store, cfg, run, NOW)
    store.save_trips("a", "2026-10-10T08:00:00Z", [_trip(taxes=20000)], "https://b.test", {})
    score_run(store, cfg, run, NOW + timedelta(minutes=5))
    (row,) = _obs(store)
    assert row["fees_minor"] == 20000  # replaced in place, not appended
    assert row["booking_link"] == "https://b.test" and row["first_seen"] == NOW.isoformat()
    (cur,) = load_current(store)
    assert cur.booking_link == "https://b.test"


def _trip(taxes):
    from tests.helpers import trip

    return trip("t1", avail_id="a", cabin="economy", miles=35000, taxes=taxes, currency="EUR")


def test_latest_price_per_flight_comes_from_whichever_run_saw_it_last(tmp_path, cfg):
    """A full run sees both flights; a later watch run sees only one. Both show on the page, each at
    the latest price anyone fetched."""
    store = Store(tmp_path / "db.sqlite")
    _scan(store, cfg, NOW, [("a", "2026-12-10", 35000, 12900), ("b", "2026-12-11", 36000, 12900)])
    _scan(store, cfg, NOW + timedelta(hours=2), [("a", "2026-12-10", 33000, 12900)])
    by_date = {s.date: s.miles for s in load_current(store)}
    assert by_date == {"2026-12-10": 33000, "2026-12-11": 36000}


def test_usual_price_is_the_median_across_dates_and_marks_a_cheap_date(tmp_path, cfg):
    store = Store(tmp_path / "db.sqlite")
    dates = [f"2026-12-{d:02d}" for d in range(1, 9)]
    flights = [(f"f{i}", d, 40000, 12900) for i, d in enumerate(dates)]
    flights.append(("cheap", "2026-12-20", 20000, 12900))
    _scan(store, cfg, NOW, flights)
    rows = {s.date: s for s in load_current(store)}
    assert rows["2026-12-20"].verdict != "Skip" and rows["2026-12-20"].route_pct < 20
    assert rows["2026-12-01"].route_pct > 40


def test_flights_in_the_past_or_long_unseen_are_not_current(tmp_path, cfg):
    store = Store(tmp_path / "db.sqlite")
    _scan(store, cfg, NOW - timedelta(days=40), [("old", "2026-12-10", 35000, 12900)])
    _scan(store, cfg, NOW, [("past", "2026-10-01", 35000, 12900), ("ok", "2026-12-12", 1, 100)])
    assert {s.availability_id for s in load_current(store)} == {"ok"}


def test_first_ever_run_flags_nothing_as_new(tmp_path, cfg):
    store = Store(tmp_path / "db.sqlite")
    _scan(store, cfg, NOW, [("a", "2026-12-10", 35000, 12900)])
    assert [s.change for s in load_current(store)] == [""]
    _scan(store, cfg, NOW + timedelta(hours=1), [("b", "2026-12-11", 35000, 12900)])
    assert {s.date: s.change for s in load_current(store)} == {
        "2026-12-10": "",
        "2026-12-11": "New",
    }


def test_new_fx_rate_does_not_reprice_history(tmp_path, cfg, default_config_dict):
    store = Store(tmp_path / "db.sqlite")
    _scan(store, cfg, NOW, [("a", "2026-12-10", 35000, 12900)])
    other = config(default_config_dict, usd_to_eur=0.5, relative={"min_samples": 3})
    run = store.start_run("watch", "{}", now=NOW + timedelta(hours=1))
    store.save_availability(
        run, avail("a", date="2026-12-10", taxes={"economy": 12900}, economy=35000), "watchlist"
    )
    rows, _ = current_rows(store, other, run)
    counts = record_observations(store, run, rows, NOW + timedelta(hours=1))
    assert counts == {"new": 0, "changed": 0, "unchanged": 1}
    (cur,) = load_current(store)
    assert cur.fees_eur == pytest.approx(129 * 0.92)  # still the rate in force when it was scored

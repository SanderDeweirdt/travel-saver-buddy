"""Observations and current offers: one latest price per flight, compared with the usual price."""

from datetime import UTC, datetime, timedelta

import pytest

from mmscan.offers import ensure_current, load_current, record_observations
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


def test_backfill_collapses_result_history_into_price_states(tmp_path):
    from mmscan.scoring import SCORED_COLUMNS, column_values
    from tests.helpers import scored

    store = Store(tmp_path / "db.sqlite")
    runs = [store.start_run("watch", "{}", now=NOW + timedelta(hours=h)) for h in range(4)]
    ph = ",".join("?" * (len(SCORED_COLUMNS) + 1))
    sql = f"INSERT INTO results(run_id, {', '.join(SCORED_COLUMNS)}) VALUES ({ph})"
    totals = [(1000, 50.0), (1000, 50.0), (900, 50.0), (900, 50.0)]  # unchanged, drop, unchanged
    for run, (miles, fees) in zip(runs, totals, strict=True):
        s = scored(miles * 1.16 + fees, cabin="economy", miles=miles, fees=fees, id="a")
        store.conn.execute(sql, (run, *column_values(s, SCORED_COLUMNS)))
    other = scored(500.0, date="2026-12-12", cabin="economy", miles=300, fees=20.0, id="b")
    store.conn.execute(sql, (runs[0], *column_values(other, SCORED_COLUMNS)))
    store.conn.execute("DELETE FROM observations")
    store.conn.execute("DELETE FROM schema_version")
    store.conn.execute("INSERT INTO schema_version(version) VALUES (2)")
    store.conn.commit()

    store.migrate()

    rows = store.conn.execute("SELECT * FROM observations WHERE date='2026-12-10' ORDER BY id")
    rows = rows.fetchall()
    assert [(r["miles"], r["run_id"]) for r in rows] == [(1000, runs[0]), (900, runs[2])]
    assert rows[0]["first_seen"] == (NOW).isoformat()
    assert rows[0]["last_seen"] == (NOW + timedelta(hours=1)).isoformat()
    assert rows[1]["last_seen"] == (NOW + timedelta(hours=3)).isoformat()
    assert store.conn.execute("SELECT count(*) FROM observations").fetchone()[0] == 3
    assert rows[0]["fees_minor"] is None and rows[0]["fees_eur"] == 50.0


def test_purge_drops_observations_not_seen_for_180_days(tmp_path, cfg):
    store = Store(tmp_path / "db.sqlite")
    _scan(store, cfg, NOW - timedelta(days=200), [("old", "2026-12-10", 35000, 12900)])
    _scan(store, cfg, NOW, [("new", "2026-12-11", 35000, 12900)])
    store.purge_older_than(180, now=NOW)
    assert [r["date"] for r in _obs(store)] == ["2026-12-11"]


def test_ensure_current_fills_an_empty_table_from_observations(tmp_path, cfg):
    store = Store(tmp_path / "db.sqlite")
    _scan(store, cfg, NOW, [("a", "2026-12-10", 35000, 12900)])
    store.conn.execute("DELETE FROM current_offers")  # as right after the migration
    store.conn.commit()
    assert load_current(store) == []
    assert ensure_current(store, cfg, NOW) is True
    (cur,) = load_current(store)
    assert cur.availability_id == "a" and cur.change == ""
    assert ensure_current(store, cfg, NOW) is False  # nothing to do the second time


def test_dashboard_start_fills_current_offers(tmp_path, default_config_dict, write_config):
    from mmscan.web.app import create_app
    from mmscan.web.settings import WebSettings

    cfg_path = write_config(default_config_dict)
    path = tmp_path / "web.db"
    store = Store(path)
    _scan(
        store,
        config(default_config_dict, relative={"min_samples": 3}),
        datetime.now(UTC),
        [("a", "2026-12-10", 35000, 12900)],
    )
    store.conn.execute("DELETE FROM current_offers")
    store.conn.commit()
    store.close()
    create_app(WebSettings("pw", "s" * 32, path, cfg_path))
    check = Store(path, readonly=True)
    assert len(load_current(check)) == 1


def test_each_program_keeps_its_own_price_and_mile_value(default_config_dict, tmp_path):
    c = config(
        default_config_dict,
        programs={"singapore": {"mile_cost_eur_cents": 2.0, "label": "KrisFlyer"}},
    )
    store = Store(tmp_path / "db.sqlite")
    run = store.start_run("watch", "{}", now=NOW)
    for id_, source, miles in (("a", "lufthansa", 10000), ("b", "singapore", 10000)):
        store.save_availability(
            run,
            {
                **avail(id_, date="2026-12-10", taxes={"economy": 5000}, economy=miles),
                "Source": source,
            },
            "watchlist",
        )
    score_run(store, c, run, NOW)

    by_source = {s.source: s for s in load_current(store)}
    assert set(by_source) == {"lufthansa", "singapore"}
    assert by_source["lufthansa"].total_eur == pytest.approx(10000 * 1.16 / 100 + 50 * 0.92)
    assert by_source["singapore"].total_eur == pytest.approx(10000 * 2.0 / 100 + 50 * 0.92)
    assert c.program_label("singapore") == "KrisFlyer" and c.program_label(None) == "M&M"


def test_database_from_before_programs_were_stored_is_tagged_miles_and_more(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    store.conn.execute("DELETE FROM schema_version")
    store.conn.execute("INSERT INTO schema_version(version) VALUES (3)")
    store.conn.execute(
        "INSERT INTO observations(key, first_seen, last_seen, cabin, source) "
        "VALUES ('MUC|SIN|2026-12-10|economy', 'x', 'x', 'economy', NULL)"
    )
    store.conn.commit()

    assert store.migrate() == 4
    assert store.conn.execute("SELECT source FROM observations").fetchone()[0] == "lufthansa"

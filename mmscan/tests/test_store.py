from datetime import UTC, datetime, timedelta

from mmscan.store import Store

NOW = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)


def test_schema_creates(tmp_path):
    store = Store(tmp_path / "data" / "mmscan.db")
    tables = {r[0] for r in store.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"runs", "api_calls", "availabilities", "trip_fetches", "trips", "results"} <= tables


def test_calls_today_counts_utc_day(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    run = store.start_run("scan", "{}", now=NOW)
    store.record_call(run, "/x", {}, 200, 5, 1, 999, now=NOW.replace(hour=0, minute=1))
    store.record_call(run, "/x", {}, 200, 5, 1, 998, now=NOW)
    store.record_call(run, "/x", {}, 200, 5, 1, 997, now=NOW - timedelta(hours=12, minutes=1))
    assert store.calls_today(NOW) == 2


def test_last_rate_remaining(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    assert store.last_rate_remaining() is None
    store.record_call(None, "/x", {}, 200, 5, 1, 950, now=NOW - timedelta(minutes=1))
    store.record_call(None, "/x", {}, 500, 5, None, None, now=NOW)
    assert store.last_rate_remaining() == 950


def test_purge_removes_old_runs_and_children(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    old = store.start_run("scan", "{}", now=NOW - timedelta(days=181))
    new = store.start_run("scan", "{}", now=NOW)
    for run in (old, new):
        store.conn.execute(
            "INSERT INTO availabilities(run_id, id, origin_kind, raw_json) VALUES (?,?,?,?)",
            (run, f"a{run}", "region", "{}"),
        )
    store.conn.execute(
        "INSERT INTO trip_fetches(availability_id, updated_at, fetched_at, status) "
        "VALUES ('a1','u',?, 'ok')",
        ((NOW - timedelta(days=181)).isoformat(),),
    )
    store.conn.execute(
        "INSERT INTO trips(id, availability_id, updated_at, raw_json) VALUES ('t1','a1','u','{}')"
    )
    store.purge_older_than(180, now=NOW)
    runs = [r[0] for r in store.conn.execute("SELECT id FROM runs")]
    avs = [r[0] for r in store.conn.execute("SELECT id FROM availabilities")]
    assert runs == [new]
    assert avs == [f"a{new}"]
    assert store.conn.execute("SELECT count(*) FROM trips").fetchone()[0] == 0
    assert store.conn.execute("SELECT count(*) FROM trip_fetches").fetchone()[0] == 0


def test_finish_run_records_status(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    run = store.start_run("scan", "{}", now=NOW)
    store.finish_run(run, "partial", {"calls": 3}, ["cap reached"], now=NOW)
    row = store.conn.execute("SELECT status, stats_json, warnings_json FROM runs").fetchone()
    assert row["status"] == "partial"
    assert '"calls": 3' in row["stats_json"]
    assert "cap reached" in row["warnings_json"]


def test_price_checks_round_trip(tmp_path):
    from mmscan.store import Store

    s = Store(tmp_path / "p.db")
    assert s.price_checks() == []
    s.add_price_check("lh", 6000, 17000, "MUC-SIN", "business", "seen on the site")
    (row,) = s.price_checks()
    assert row["carrier"] == "LH" and row["live_miles"] == 17000 and row["route"] == "MUC-SIN"
    s.close()


def test_migrations_stamp_a_fresh_database(tmp_path):
    from mmscan.store import MIGRATIONS

    store = Store(tmp_path / "db.sqlite")
    assert store.schema_version() == MIGRATIONS[-1][0]
    tables = {r[0] for r in store.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"observations", "current_offers", "schema_version"} <= tables
    store.close()
    again = Store(tmp_path / "db.sqlite")  # reopening applies nothing and keeps one version row
    assert again.conn.execute("SELECT count(*) FROM schema_version").fetchone()[0] == 1


def test_migrations_upgrade_a_pre_migration_database(tmp_path):
    import sqlite3

    from mmscan.store import SCHEMA

    path = tmp_path / "old.sqlite"
    old = sqlite3.connect(path)
    old.executescript(SCHEMA)  # a database made before schema_version existed
    old.execute("INSERT INTO runs(kind, started_at, status) VALUES ('scan', 'x', 'ok')")
    old.commit()
    old.close()
    store = Store(path)
    assert store.schema_version() >= 2
    assert store.conn.execute("SELECT count(*) FROM runs").fetchone()[0] == 1  # data kept
    assert store.conn.execute("SELECT count(*) FROM observations").fetchone()[0] == 0


def test_purge_drops_per_run_detail_after_two_weeks_but_keeps_the_run(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    mid = store.start_run("scan", "{}", now=NOW - timedelta(days=30))
    store.conn.execute(
        "INSERT INTO availabilities(run_id, id, origin_kind, raw_json) VALUES (?,?,?,?)",
        (mid, "a", "region", "{}"),
    )
    store.purge_older_than(180, now=NOW)
    assert store.conn.execute("SELECT count(*) FROM runs").fetchone()[0] == 1
    assert store.conn.execute("SELECT count(*) FROM availabilities").fetchone()[0] == 0

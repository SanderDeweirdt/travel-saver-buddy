"""Store behaviour on both backends. Postgres cases run when TEST_DATABASE_URL is set."""

from datetime import UTC, datetime, timedelta

import pytest

from mmscan.db import translate
from mmscan.scoring import score_run
from mmscan.store import Store
from tests.helpers import avail, config, trip

NOW = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)


def test_calls_today_and_rate_remaining(backend_store):
    s = backend_store
    run = s.start_run("scan", "{}", now=NOW)
    s.record_call(run, "/x", {"a": 1}, 200, 5, 1, 999, now=NOW.replace(hour=0, minute=1))
    s.record_call(run, "/x", {}, 200, 5, 1, 998, now=NOW - timedelta(minutes=1))
    s.record_call(run, "/x", {}, 500, 5, None, None, now=NOW)
    s.record_call(run, "/x", {}, 200, 5, 1, 997, now=NOW - timedelta(hours=12, minutes=1))
    assert s.calls_today(NOW) == 3
    assert s.last_rate_remaining() == 998


def test_run_lifecycle_and_merge(backend_store):
    s = backend_store
    run = s.start_run("run", "{}", now=NOW)
    assert s.run_info(run)["status"] == "running"
    s.finish_run(run, "ok", {"calls": 3}, ["w1"], now=NOW)
    s.merge_run(run, "partial", {"scored": 2}, ["w1", "w2"], now=NOW)
    row = s.run_info(run)
    assert row["status"] == "partial" and row["kind"] == "run"
    assert row[1] == "run"  # positional access works as well
    assert '"scored": 2' in row["stats_json"] and '"calls": 3' in row["stats_json"]
    assert row["warnings_json"] == '["w1", "w2"]'
    assert s.run_info(run + 100) is None


def test_save_availability_and_trips_replace(backend_store):
    s = backend_store
    run = s.start_run("watch", "{}", now=NOW)
    s.save_availability(run, avail("a", business=60000), "watchlist")
    s.save_availability(run, avail("a", business=55000), "watchlist")  # replaces
    assert s.scan_counts(run) == {
        "region_results": 0,
        "watchlist_results": 1,
        "watchlist_trips": 0,
    }
    u = "2026-10-10T08:00:00Z"
    s.save_trips("a", u, [trip("t1", taxes=100)], "https://x.test", {"k": 1}, now=NOW)
    s.save_trips("a", u, [trip("t1", taxes=200)], "https://x.test", {"k": 2}, now=NOW)
    assert s.has_fetch("a", u) and not s.has_fetch("a", "other")
    rows = s.conn.execute("SELECT total_taxes FROM trips").fetchall()
    assert [r["total_taxes"] for r in rows] == [200]
    assert s.scan_counts(run)["watchlist_trips"] == 1
    s.mark_expired("b", u, now=NOW)
    assert (
        s.conn.execute("SELECT status FROM trip_fetches WHERE availability_id='b'").fetchone()[0]
        == "expired"
    )
    s.mark_expired("b", u, now=NOW)  # replace again, no error


def test_latest_runs_filter_by_kind(backend_store):
    s = backend_store
    full = s.start_run("run", "{}", now=NOW - timedelta(hours=2))
    watch = s.start_run("watch", "{}", now=NOW)
    for r in (full, watch):
        s.save_availability(r, avail(f"a{r}", business=60000), "region")
    assert s.latest_scanned_run() == watch
    assert s.latest_scanned_run(("scan", "run")) == full
    assert s.latest_scored_run() is None


def test_purge_removes_old_rows(backend_store):
    s = backend_store
    old = s.start_run("scan", "{}", now=NOW - timedelta(days=181))
    new = s.start_run("scan", "{}", now=NOW)
    for r in (old, new):
        s.save_availability(r, avail(f"a{r}", business=60000), "region")
        s.record_call(r, "/x", {}, 200, 1, 1, 1, now=NOW - timedelta(days=181 if r == old else 0))
    s.save_trips("a1", "u", [trip("t1", avail_id="a1")], None, {}, now=NOW - timedelta(days=181))
    s.purge_older_than(180, now=NOW)
    assert [r[0] for r in s.conn.execute("SELECT id FROM runs")] == [new]
    assert s.conn.execute("SELECT count(*) FROM availabilities").fetchone()[0] == 1
    assert s.conn.execute("SELECT count(*) FROM api_calls").fetchone()[0] == 1
    assert s.conn.execute("SELECT count(*) FROM trips").fetchone()[0] == 0
    assert s.conn.execute("SELECT count(*) FROM trip_fetches").fetchone()[0] == 0


def test_score_run_round_trips_with_history(backend_store, default_config_dict):
    s = backend_store
    cfg = config(default_config_dict, relative={"percentile_good": 20, "min_samples": 2})
    for days in (3, 2, 1, 0):
        run = s.start_run("watch", "{}", now=NOW - timedelta(days=days))
        s.save_availability(run, avail(f"a{days}", business=60000 - days * 1000), "watchlist")
        s.save_trips(
            f"a{days}",
            "2026-10-10T08:00:00Z",
            [trip(f"t{days}", avail_id=f"a{days}", miles=60000 - days * 1000, taxes=30000)],
            "https://x.test",
            {},
        )
        rows, _ = score_run(s, cfg, run, NOW - timedelta(days=days))
    (row,) = [r for r in rows if r.cabin == "business"]
    assert row.miles == 60000 and row.seats_ok is True and row.booking_link == "https://x.test"
    stored = s.conn.execute("SELECT * FROM results WHERE run_id=?", (run,)).fetchall()
    assert len(stored) == len(rows)
    assert isinstance(stored[0]["fees_eur"], float) and stored[0]["expired"] in (0, False)
    assert s.latest_scored_run() == run


def test_read_only_store_cannot_write(backend_store, tmp_path):
    s = backend_store
    s.start_run("scan", "{}", now=NOW)
    target = str(s.conn._conn.info.dsn) if s.postgres else s.path
    ro = Store(_conninfo(s) if s.postgres else target, readonly=True)
    assert ro.latest_scanned_run() is None
    with pytest.raises(Exception, match="read-only|readonly|read only"):
        ro.start_run("scan", "{}")


def _conninfo(store: Store) -> str:
    import os

    return os.environ["TEST_DATABASE_URL"]


def test_translate_upsert_and_placeholders():
    sql = translate(
        "INSERT OR REPLACE INTO trip_fetches(availability_id, updated_at, status) VALUES (?,?,?)"
    )
    assert sql.endswith(
        "ON CONFLICT (availability_id, updated_at) DO UPDATE SET status=EXCLUDED.status"
    )
    assert "%s,%s,%s" in sql and "?" not in sql
    only_keys = translate("INSERT OR REPLACE INTO trips(id, updated_at) VALUES (?,?)")
    assert only_keys.endswith("DO NOTHING")

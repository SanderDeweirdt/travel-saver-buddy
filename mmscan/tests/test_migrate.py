import os
from datetime import UTC, datetime

import pytest

from mmscan.migrate import ORDER, migrate
from mmscan.scoring import score_run
from mmscan.store import Store
from tests.helpers import avail, config, trip

NOW = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)


def test_migrate_sqlite_to_postgres_is_idempotent(tmp_path, backend_store, default_config_dict):
    if not backend_store.postgres:
        pytest.skip("needs the postgres backend")
    url = os.environ["TEST_DATABASE_URL"]
    src = Store(tmp_path / "old.db")
    cfg = config(default_config_dict)
    for _ in range(2):
        run = src.start_run("watch", "{}", now=NOW)
        src.record_call(run, "/x", {}, 200, 1, 1, 900, now=NOW)
        src.save_availability(run, avail("a", business=60000), "watchlist")
        src.save_trips("a", "2026-10-10T08:00:00Z", [trip("t1", avail_id="a")], None, {})
        score_run(src, cfg, run, NOW)
    src.close()

    first = migrate(tmp_path / "old.db", url)
    assert {t: n for t, n, _ in first}["runs"] == 2
    assert all(copied == total for _, copied, total in first)
    again = migrate(tmp_path / "old.db", url)
    assert all(copied == 0 for _, copied, _ in again)
    assert [t for t, _, _ in again] == list(ORDER)

    dest = backend_store
    assert dest.conn.execute("SELECT count(*) FROM results").fetchone()[0] == 2
    # The identity sequence continues after the copied ids
    assert dest.start_run("watch", "{}", now=NOW) == 3

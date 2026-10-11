"""SQLite storage: runs, raw API objects, trips, scored results and API calls."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT,
    config_json TEXT,
    stats_json TEXT,
    warnings_json TEXT
);
CREATE TABLE IF NOT EXISTS api_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER,
    ts TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    params_json TEXT,
    status INTEGER,
    duration_ms INTEGER,
    results INTEGER,
    rate_remaining INTEGER
);
CREATE INDEX IF NOT EXISTS api_calls_ts ON api_calls(ts);
CREATE TABLE IF NOT EXISTS availabilities (
    run_id INTEGER NOT NULL,
    id TEXT NOT NULL,
    origin TEXT,
    destination TEXT,
    origin_region TEXT,
    destination_region TEXT,
    date TEXT,
    source TEXT,
    updated_at TEXT,
    origin_kind TEXT NOT NULL CHECK (origin_kind IN ('region', 'watchlist')),
    raw_json TEXT NOT NULL,
    PRIMARY KEY (run_id, id)
);
CREATE TABLE IF NOT EXISTS trip_fetches (
    availability_id TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('ok', 'expired')),
    booking_link TEXT,
    raw_json TEXT,
    PRIMARY KEY (availability_id, updated_at)
);
CREATE TABLE IF NOT EXISTS trips (
    id TEXT NOT NULL,
    availability_id TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    cabin TEXT,
    mileage_cost INTEGER,
    total_taxes INTEGER,
    taxes_currency TEXT,
    remaining_seats INTEGER,
    stops INTEGER,
    carriers TEXT,
    flight_numbers TEXT,
    departs_at TEXT,
    arrives_at TEXT,
    total_duration INTEGER,
    raw_json TEXT NOT NULL,
    PRIMARY KEY (id, updated_at)
);
CREATE INDEX IF NOT EXISTS trips_avail ON trips(availability_id, updated_at);
CREATE TABLE IF NOT EXISTS results (
    run_id INTEGER NOT NULL,
    availability_id TEXT NOT NULL,
    cabin TEXT NOT NULL,
    date TEXT,
    origin TEXT,
    destination TEXT,
    origin_region TEXT,
    destination_region TEXT,
    miles INTEGER,
    fees_eur REAL,
    fee_estimated INTEGER,
    total_eur REAL,
    seats INTEGER,
    stops INTEGER,
    carriers TEXT,
    flight_numbers TEXT,
    departs_at TEXT,
    arrives_at TEXT,
    booking_link TEXT,
    updated_at TEXT,
    route_good INTEGER,
    destination_good INTEGER,
    ceiling_good INTEGER,
    seats_ok INTEGER,
    direct INTEGER,
    chart_rate INTEGER,
    route_pct REAL,
    destination_pct REAL,
    verdict TEXT,
    cash_fare_eur REAL,
    saving_eur REAL,
    value_cents REAL,
    value_band TEXT,
    change TEXT,
    expired INTEGER DEFAULT 0,
    PRIMARY KEY (run_id, availability_id, cabin)
);
"""


def utcnow() -> datetime:
    return datetime.now(UTC)


class Store:
    def __init__(self, path: Path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # Runs

    def start_run(self, kind: str, config_json: str, now: datetime | None = None) -> int:
        cur = self.conn.execute(
            "INSERT INTO runs(kind, started_at, status, config_json) VALUES (?,?,?,?)",
            (kind, (now or utcnow()).isoformat(), "running", config_json),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def finish_run(
        self,
        run_id: int,
        status: str,
        stats: dict,
        warnings: list[str],
        now: datetime | None = None,
    ) -> None:
        self.conn.execute(
            "UPDATE runs SET finished_at=?, status=?, stats_json=?, warnings_json=? WHERE id=?",
            (
                (now or utcnow()).isoformat(),
                status,
                json.dumps(stats, sort_keys=True),
                json.dumps(warnings),
                run_id,
            ),
        )
        self.conn.commit()

    # API calls

    def record_call(
        self,
        run_id: int | None,
        endpoint: str,
        params: dict,
        status: int | None,
        duration_ms: int,
        results: int | None,
        rate_remaining: int | None,
        now: datetime | None = None,
    ) -> None:
        self.conn.execute(
            "INSERT INTO api_calls(run_id, ts, endpoint, params_json, status, duration_ms, "
            "results, rate_remaining) VALUES (?,?,?,?,?,?,?,?)",
            (
                run_id,
                (now or utcnow()).isoformat(),
                endpoint,
                json.dumps(params, sort_keys=True),
                status,
                duration_ms,
                results,
                rate_remaining,
            ),
        )
        self.conn.commit()

    def calls_today(self, now: datetime | None = None) -> int:
        now = (now or utcnow()).astimezone(UTC)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        row = self.conn.execute(
            "SELECT count(*) FROM api_calls WHERE ts >= ? AND ts < ?",
            (start.isoformat(), end.isoformat()),
        ).fetchone()
        return int(row[0])

    def last_rate_remaining(self) -> int | None:
        row = self.conn.execute(
            "SELECT rate_remaining FROM api_calls WHERE rate_remaining IS NOT NULL "
            "ORDER BY ts DESC, id DESC LIMIT 1"
        ).fetchone()
        return None if row is None else int(row[0])

    # Retention

    def purge_older_than(self, days: int = 180, now: datetime | None = None) -> None:
        cutoff = ((now or utcnow()) - timedelta(days=days)).isoformat()
        old_runs = "SELECT id FROM runs WHERE started_at < ?"
        for table in ("availabilities", "results"):
            self.conn.execute(f"DELETE FROM {table} WHERE run_id IN ({old_runs})", (cutoff,))
        self.conn.execute("DELETE FROM runs WHERE started_at < ?", (cutoff,))
        self.conn.execute("DELETE FROM api_calls WHERE ts < ?", (cutoff,))
        self.conn.execute(
            "DELETE FROM trips WHERE (availability_id, updated_at) IN "
            "(SELECT availability_id, updated_at FROM trip_fetches WHERE fetched_at < ?)",
            (cutoff,),
        )
        self.conn.execute("DELETE FROM trip_fetches WHERE fetched_at < ?", (cutoff,))
        self.conn.commit()

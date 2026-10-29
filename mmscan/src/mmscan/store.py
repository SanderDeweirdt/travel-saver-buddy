"""Storage: runs, raw API objects, trips, scored results and API calls.

SQLite for local use; Postgres when the target is a `postgres://` URL (see `mmscan.db`).
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from mmscan.db import SCHEMA_LOCK, PgConnection, is_postgres_url
from mmscan.models import Trip

FULL_RUNS = ("scan", "run")  # watch runs hold only the watchlist

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
CREATE INDEX IF NOT EXISTS results_route ON results(origin, destination, cabin, run_id);
CREATE TABLE IF NOT EXISTS price_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    checked_at TEXT NOT NULL,
    carrier TEXT NOT NULL,
    route TEXT,
    cabin TEXT,
    cached_miles INTEGER NOT NULL,
    live_miles INTEGER NOT NULL,
    note TEXT
);
CREATE INDEX IF NOT EXISTS runs_started ON runs(started_at);
CREATE INDEX IF NOT EXISTS api_calls_run ON api_calls(run_id);
CREATE INDEX IF NOT EXISTS trip_fetches_fetched ON trip_fetches(fetched_at);
"""

# Facts: one row per distinct price state of a flight key (origin|destination|date|cabin). A rescan
# that sees the same state bumps last_seen instead of adding a row, so a row covers
# first_seen..last_seen. Totals are never stored; they are computed from miles and fees.
OBSERVATIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL,
    run_id INTEGER,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    availability_id TEXT,
    origin TEXT,
    destination TEXT,
    origin_region TEXT,
    destination_region TEXT,
    date TEXT,
    cabin TEXT NOT NULL,
    miles INTEGER,
    fees_minor INTEGER,
    currency TEXT,
    fees_eur REAL,
    fee_estimated INTEGER NOT NULL DEFAULT 0,
    expired INTEGER NOT NULL DEFAULT 0,
    seats INTEGER,
    stops INTEGER,
    direct INTEGER,
    carriers TEXT,
    flight_numbers TEXT,
    departs_at TEXT,
    arrives_at TEXT,
    booking_link TEXT,
    source_updated_at TEXT
);
CREATE INDEX IF NOT EXISTS observations_key ON observations(key, id);
CREATE INDEX IF NOT EXISTS observations_last_seen ON observations(last_seen);
CREATE TABLE IF NOT EXISTS current_offers (
    key TEXT PRIMARY KEY,
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
    first_seen TEXT,
    last_seen TEXT
);
CREATE INDEX IF NOT EXISTS current_offers_route ON current_offers(origin, destination, cabin);
"""


def _backfill_observations(store: Store) -> int:
    from mmscan.backfill import backfill_observations

    return backfill_observations(store)


# Which seats.aero program each flight came from. Everything stored before this was Miles & More.
SOURCE_TABLES = ("observations", "current_offers", "results")
SOURCE_COLUMNS = "\n".join(f"ALTER TABLE {t} ADD COLUMN source TEXT;" for t in SOURCE_TABLES)


def _add_source_columns(store: Store) -> None:
    """Migration 4. A column may already exist (a database rebuilt from the newer schema), so each
    is checked first; SQLite has no ADD COLUMN IF NOT EXISTS."""
    for table in SOURCE_TABLES:
        if store.postgres:
            store.conn.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS source TEXT")
        elif "source" not in {r[1] for r in store.conn.execute(f"PRAGMA table_info({table})")}:
            store.conn.execute(f"ALTER TABLE {table} ADD COLUMN source TEXT")
        store.conn.execute(f"UPDATE {table} SET source = 'lufthansa' WHERE source IS NULL")
    store.conn.commit()


VERSION_TABLE = "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)"

# (version, DDL script or a function(store) for data migrations). Append only; never edit one that
# has shipped. Migration 1 is the original schema, so existing databases are stamped, not rebuilt.
MIGRATIONS: list[tuple[int, str | Callable[[Store], object]]] = [
    (1, SCHEMA),
    (2, OBSERVATIONS_SCHEMA),
    (3, _backfill_observations),
    (4, _add_source_columns),
]


def pg_ddl(sql: str) -> str:
    """SQLite DDL in Postgres types: identity ids, double-precision floats."""
    return sql.replace(
        "INTEGER PRIMARY KEY AUTOINCREMENT", "BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY"
    ).replace(" REAL", " DOUBLE PRECISION")


def pg_schema() -> str:
    """The whole schema in Postgres types."""
    return pg_ddl(SCHEMA + OBSERVATIONS_SCHEMA + SOURCE_COLUMNS)


def utcnow() -> datetime:
    return datetime.now(UTC)


class Store:
    def __init__(self, target: Path | str, readonly: bool = False):
        """`target` is a SQLite file path or a postgres:// URL. A read-only store never writes,
        schema creation included."""
        self.ident = str(target)  # which database this is; used as a cache key
        self.postgres = is_postgres_url(target)
        self.readonly = readonly
        if self.postgres:
            self.path = None
            self.conn = PgConnection(str(target), readonly=readonly)
            if not readonly:
                self.migrate()
            return
        path = Path(target)
        if not readonly:
            path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        if readonly:
            self.conn.execute("PRAGMA query_only = ON")
        else:
            self.migrate()

    def schema_version(self) -> int:
        try:
            row = self.conn.execute("SELECT max(version) FROM schema_version").fetchone()
        except Exception:  # no schema_version table yet: a fresh or pre-migration database
            if self.postgres:
                self.conn.rollback()
            return 0
        return int(row[0] or 0)

    def migrate(self) -> int:
        """Apply the migrations this database has not seen. Returns the version it ends on."""
        have = self.schema_version()
        for version, script in MIGRATIONS:
            if version <= have:
                continue
            stamp = (
                f"DELETE FROM schema_version;\nINSERT INTO schema_version(version) "
                f"VALUES ({int(version)});"
            )
            if callable(script):
                if self.postgres:  # one process migrates; the others find it done
                    self.conn.execute(f"SELECT pg_advisory_xact_lock({SCHEMA_LOCK})")
                    if self.schema_version() >= version:
                        self.conn.rollback()
                        continue
                script(self)  # a data migration; its work commits before the version moves
                self.conn.executescript(f"{VERSION_TABLE};\n{stamp}")
            else:
                ddl = pg_ddl(script) if self.postgres else script
                self.conn.executescript(f"{VERSION_TABLE};\n{ddl};\n{stamp}")
            if not self.postgres:
                self.conn.commit()
        return MIGRATIONS[-1][0]

    def close(self) -> None:
        self.conn.close()

    # Runs

    def start_run(self, kind: str, config_json: str, now: datetime | None = None) -> int:
        row = self.conn.execute(
            "INSERT INTO runs(kind, started_at, status, config_json) VALUES (?,?,?,?) RETURNING id",
            (kind, (now or utcnow()).isoformat(), "running", config_json),
        ).fetchone()
        self.conn.commit()
        return int(row[0])

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

    def merge_run(
        self,
        run_id: int,
        status: str | None = None,
        stats: dict | None = None,
        warnings: list[str] | None = None,
        now: datetime | None = None,
    ) -> None:
        """Add a step's stats and warnings to a run that several commands share."""
        row = self.conn.execute(
            "SELECT status, stats_json, warnings_json FROM runs WHERE id=?", (run_id,)
        ).fetchone()
        merged = {**json.loads(row["stats_json"] or "{}"), **(stats or {})}
        warns = list(dict.fromkeys(json.loads(row["warnings_json"] or "[]") + (warnings or [])))
        self.finish_run(run_id, status or row["status"], merged, warns, now=now)

    def run_info(self, run_id: int):
        return self.conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()

    def _latest(self, table: str, kinds: tuple[str, ...] | None) -> int | None:
        sql = f"SELECT max(t.run_id) FROM {table} t JOIN runs u ON u.id = t.run_id"
        args: tuple = ()
        if kinds:
            sql += f" WHERE u.kind IN ({','.join('?' * len(kinds))})"
            args = kinds
        row = self.conn.execute(sql, args).fetchone()
        return None if row[0] is None else int(row[0])

    def latest_scanned_run(self, kinds: tuple[str, ...] | None = None) -> int | None:
        return self._latest("availabilities", kinds)

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

    # Manual price checks: what seats.aero cached against what miles-and-more.com showed

    def add_price_check(
        self,
        carrier: str,
        cached_miles: int,
        live_miles: int,
        route: str | None = None,
        cabin: str | None = None,
        note: str | None = None,
        now: datetime | None = None,
    ) -> None:
        self.conn.execute(
            "INSERT INTO price_checks(checked_at, carrier, route, cabin, cached_miles, "
            "live_miles, note) VALUES (?,?,?,?,?,?,?)",
            (
                (now or utcnow()).isoformat(),
                carrier.upper(),
                route,
                cabin,
                cached_miles,
                live_miles,
                note,
            ),
        )
        self.conn.commit()

    def price_checks(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT checked_at, carrier, route, cabin, cached_miles, live_miles, note "
            "FROM price_checks ORDER BY id"
        ).fetchall()
        return [dict(zip(rows[0].keys(), tuple(r), strict=True)) for r in rows] if rows else []

    # Retention

    def purge_older_than(
        self, days: int = 180, now: datetime | None = None, detail_days: int = 14
    ) -> None:
        """Drop old history. The per-run copies (`availabilities` with their raw JSON, `results`)
        are only read for the latest run; the price history lives in `observations`. They go after
        `detail_days` so the database does not fill up; the rest goes after `days`."""
        now = now or utcnow()
        cutoff = (now - timedelta(days=days)).isoformat()
        detail_cutoff = (now - timedelta(days=min(days, detail_days))).isoformat()
        stale_runs = "SELECT id FROM runs WHERE started_at < ?"
        for table in ("availabilities", "results"):
            self.conn.execute(
                f"DELETE FROM {table} WHERE run_id IN ({stale_runs})", (detail_cutoff,)
            )
        self.conn.execute("DELETE FROM runs WHERE started_at < ?", (cutoff,))
        self.conn.execute("DELETE FROM api_calls WHERE ts < ?", (cutoff,))
        self.conn.execute("DELETE FROM observations WHERE last_seen < ?", (cutoff,))
        self.conn.execute(
            "DELETE FROM trips WHERE (availability_id, updated_at) IN "
            "(SELECT availability_id, updated_at FROM trip_fetches WHERE fetched_at < ?)",
            (cutoff,),
        )
        self.conn.execute("DELETE FROM trip_fetches WHERE fetched_at < ?", (cutoff,))
        self.conn.commit()

    # Scan results

    def save_availability(self, run_id: int, avail: dict, kind: str) -> None:
        route = avail.get("Route") or {}
        self.conn.execute(
            "INSERT OR REPLACE INTO availabilities(run_id, id, origin, destination, "
            "origin_region, destination_region, date, source, updated_at, origin_kind, raw_json) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                run_id,
                str(avail["ID"]),
                route.get("OriginAirport"),
                route.get("DestinationAirport"),
                route.get("OriginRegion"),
                route.get("DestinationRegion"),
                avail.get("Date"),
                avail.get("Source"),
                avail.get("UpdatedAt"),
                kind,
                json.dumps(avail, sort_keys=True),
            ),
        )
        self.conn.commit()

    def scan_counts(self, run_id: int) -> dict:
        counts = {"region_results": 0, "watchlist_results": 0}
        for kind, n in self.conn.execute(
            "SELECT origin_kind, count(*) FROM availabilities WHERE run_id=? GROUP BY origin_kind",
            (run_id,),
        ):
            counts[f"{kind}_results"] = n
        row = self.conn.execute(
            "SELECT count(*) FROM trips t JOIN availabilities a "
            "ON a.id = t.availability_id AND a.updated_at = t.updated_at "
            "WHERE a.run_id=? AND a.origin_kind='watchlist'",
            (run_id,),
        ).fetchone()
        counts["watchlist_trips"] = int(row[0])
        return counts

    def has_fetch(self, avail_id: str, updated_at: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM trip_fetches WHERE availability_id=? AND updated_at=?",
            (avail_id, updated_at),
        ).fetchone()
        return row is not None

    def mark_expired(self, avail_id: str, updated_at: str, now: datetime | None = None) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO trip_fetches(availability_id, updated_at, fetched_at, "
                "status, booking_link, raw_json) VALUES (?,?,?,?,?,?)",
                (avail_id, updated_at, (now or utcnow()).isoformat(), "expired", None, None),
            )

    def save_trips(
        self,
        avail_id: str,
        updated_at: str,
        trips: list[Trip],
        booking_link: str | None,
        raw: object,
        now: datetime | None = None,
    ) -> None:
        """Store one availability's trips and its fetch row in one transaction."""
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO trip_fetches(availability_id, updated_at, fetched_at, "
                "status, booking_link, raw_json) VALUES (?,?,?,?,?,?)",
                (
                    avail_id,
                    updated_at,
                    (now or utcnow()).isoformat(),
                    "ok",
                    booking_link,
                    json.dumps(raw, sort_keys=True),
                ),
            )
            self.conn.executemany(
                "INSERT OR REPLACE INTO trips(id, availability_id, updated_at, cabin, "
                "mileage_cost, total_taxes, taxes_currency, remaining_seats, stops, carriers, "
                "flight_numbers, departs_at, arrives_at, total_duration, raw_json) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [
                    (
                        t.id,
                        avail_id,
                        updated_at,
                        t.cabin,
                        t.miles,
                        t.taxes_minor,
                        t.currency,
                        t.seats,
                        t.stops,
                        t.carriers,
                        t.flight_numbers,
                        t.departs_at,
                        t.arrives_at,
                        t.total_duration,
                        json.dumps(t.raw, sort_keys=True),
                    )
                    for t in trips
                ],
            )

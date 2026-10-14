"""Copy a SQLite database into Postgres (the `migrate-sqlite` command)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from mmscan.store import Store

# Parents before children; each table's primary key is its idempotency guard.
ORDER = ("runs", "api_calls", "availabilities", "trip_fetches", "trips", "results", "price_checks")
BATCH = 1000


def migrate(source: Path, url: str) -> list[tuple[str, int, int]]:
    """Returns (table, rows copied, rows in source) per table."""
    src = sqlite3.connect(source)
    src.row_factory = sqlite3.Row
    dest = Store(url)
    out = []
    try:
        for table in ORDER:
            total = src.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            cols = [r[1] for r in src.execute(f"PRAGMA table_info({table})")]
            sql = (
                f"INSERT INTO {table}({', '.join(cols)}) VALUES ({','.join('?' * len(cols))}) "
                "ON CONFLICT DO NOTHING"
            )
            copied = 0
            cursor = src.execute(f"SELECT {', '.join(cols)} FROM {table}")
            while batch := cursor.fetchmany(BATCH):
                with dest.conn:
                    for row in batch:
                        cur = dest.conn.execute(sql, tuple(row))
                        copied += cur.rowcount
            out.append((table, copied, total))
        with dest.conn:
            for table in ("runs", "api_calls", "price_checks"):
                dest.conn.execute(
                    f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                    f"GREATEST((SELECT max(id) FROM {table}), 1))"
                )
    finally:
        src.close()
        dest.close()
    return out

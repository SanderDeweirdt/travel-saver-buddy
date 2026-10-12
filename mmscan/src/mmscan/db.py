"""Postgres connection that speaks the SQLite flavour of SQL the store and scoring code use.

The code base writes `?` placeholders, `INSERT OR REPLACE` and reads rows by name or position.
`PgConnection` mirrors the slice of the `sqlite3.Connection` API those call sites use
(`execute`, `executemany`, `commit`, `with conn:`) and translates the SQL, so one set of
statements serves both backends.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from functools import lru_cache
from typing import Any

import psycopg

# Conflict targets for INSERT OR REPLACE, which has no Postgres spelling.
PRIMARY_KEYS = {
    "availabilities": ("run_id", "id"),
    "trip_fetches": ("availability_id", "updated_at"),
    "trips": ("id", "updated_at"),
    "results": ("run_id", "availability_id", "cabin"),
}
_REPLACE = re.compile(r"^\s*INSERT OR REPLACE INTO (\w+)\s*\(([^)]*)\)(.*)$", re.DOTALL | re.I)
SCHEMA_LOCK = 7_348_201  # arbitrary advisory-lock key: serialises concurrent schema creation


def is_postgres_url(target: object) -> bool:
    return isinstance(target, str) and target.startswith(("postgres://", "postgresql://"))


@lru_cache(maxsize=256)
def translate(sql: str) -> str:
    """SQLite SQL to Postgres SQL: placeholders and INSERT OR REPLACE."""
    m = _REPLACE.match(sql)
    if m:
        table, cols_text, rest = m.groups()
        cols = [c.strip() for c in cols_text.split(",")]
        keys = PRIMARY_KEYS[table]
        updates = [f"{c}=EXCLUDED.{c}" for c in cols if c not in keys]
        action = f"DO UPDATE SET {', '.join(updates)}" if updates else "DO NOTHING"
        sql = f"INSERT INTO {table}({cols_text}){rest} ON CONFLICT ({', '.join(keys)}) {action}"
    return sql.replace("%", "%%").replace("?", "%s")


def _params(params: Sequence[Any]) -> tuple:
    """Booleans go into INTEGER columns as 0/1, as SQLite stores them."""
    return tuple(int(p) if isinstance(p, bool) else p for p in params)


class _Row(tuple):
    """A result row readable by position and by column name, like `sqlite3.Row`."""

    _names: tuple[str, ...] = ()

    def __getitem__(self, key):
        if isinstance(key, str):
            return tuple.__getitem__(self, self._names.index(key))
        return tuple.__getitem__(self, key)

    def keys(self) -> list[str]:
        return list(self._names)


@lru_cache(maxsize=256)
def _row_class(names: tuple[str, ...]) -> type[_Row]:
    return type("Row", (_Row,), {"_names": names})


def _row_factory(cursor):
    cls = _row_class(tuple(c.name for c in cursor.description or ()))
    return lambda values: cls(values)


class PgConnection:
    def __init__(self, url: str, readonly: bool = False):
        self._conn = psycopg.connect(url, row_factory=_row_factory)
        if readonly:
            self._conn.read_only = True

    def execute(self, sql: str, params: Sequence[Any] = ()):
        return self._conn.execute(translate(sql), _params(params))

    def executemany(self, sql: str, seq: Iterable[Sequence[Any]]):
        cur = self._conn.cursor()
        cur.executemany(translate(sql), [_params(p) for p in seq])
        return cur

    def executescript(self, script: str) -> None:
        """Run `;`-separated DDL in one transaction, serialised across processes."""
        with self._conn.transaction():
            self._conn.execute("SELECT pg_advisory_xact_lock(%s)", (SCHEMA_LOCK,))
            for statement in script.split(";"):
                if statement.strip():
                    self._conn.execute(statement)

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> PgConnection:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is None:
            self._conn.commit()
        else:
            self._conn.rollback()

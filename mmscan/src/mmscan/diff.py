"""New and Cheaper, against the last time each route, date and cabin was seen.

Comparing per result rather than against one previous run keeps hourly watchlist runs and daily
full runs from flagging each other's results as New, so each deal is reported once."""

from __future__ import annotations

from typing import Literal

from mmscan.store import Store

CHEAPER_DROP = 0.05


def previous_run_id(store: Store, run_id: int) -> int | None:
    """The most recent earlier run that has scored results (builder call 11)."""
    row = store.conn.execute(
        "SELECT max(run_id) FROM results WHERE run_id < ?", (run_id,)
    ).fetchone()
    return None if row[0] is None else int(row[0])


def previous_totals(store: Store, run_id: int) -> dict[tuple, float | None] | None:
    """Last known total per (origin, destination, date, cabin) over every earlier scored run.
    A key seen only without a total maps to None. None overall when no earlier run was scored."""
    rows = store.conn.execute(
        "SELECT origin, destination, date, cabin, total_eur FROM results "
        "WHERE run_id < ? AND expired = 0 ORDER BY run_id",
        (run_id,),
    ).fetchall()
    if not rows:
        return None
    last: dict[tuple, float | None] = {}
    for r in rows:
        key = (r[0], r[1], r[2], r[3])
        if r[4] is not None or key not in last:
            last[key] = r[4]
    return last


def change(prev_total: float | None, total: float) -> Literal["New", "Cheaper", ""]:
    if prev_total is None:
        return "New"
    if prev_total > 0 and (prev_total - total) / prev_total >= CHEAPER_DROP - 1e-9:
        return "Cheaper"
    return ""


def change_for(prev: dict[tuple, float | None] | None, key: tuple, total: float | None) -> str:
    """Blank when nothing was scored before, there is no total, or the key was only ever seen
    without a total."""
    if prev is None or total is None:
        return ""
    if key not in prev:
        return "New"
    if prev[key] is None:
        return ""
    return change(prev[key], total)

"""New and Cheaper, against the previous scored run."""

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
    prev = previous_run_id(store, run_id)
    if prev is None:
        return None
    rows = store.conn.execute(
        "SELECT origin, destination, date, cabin, total_eur FROM results "
        "WHERE run_id=? AND expired=0",
        (prev,),
    )
    return {(r[0], r[1], r[2], r[3]): r[4] for r in rows}


def change(prev_total: float | None, total: float) -> Literal["New", "Cheaper", ""]:
    if prev_total is None:
        return "New"
    if prev_total > 0 and (prev_total - total) / prev_total >= CHEAPER_DROP - 1e-9:
        return "Cheaper"
    return ""


def change_for(prev: dict[tuple, float | None] | None, key: tuple, total: float | None) -> str:
    """Blank when there is no previous run, no total, or the previous run had no total."""
    if prev is None or total is None:
        return ""
    if key not in prev:
        return "New"
    if prev[key] is None:
        return ""
    return change(prev[key], total)

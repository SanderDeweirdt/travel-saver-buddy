"""New and Cheaper, against the state a flight was in before the run that changed it.

`offers.rebuild_current` builds the comparison from `observations`: a flight is New when the run
created its first observation and Cheaper when the run's new state costs less than the one before.
Hourly watchlist runs and daily full runs therefore never flag each other's flights, so each deal is
reported once."""

from __future__ import annotations

from typing import Literal

DEFAULT_DROP_PCT = 5.0  # config: drops.min_pct


def change(
    prev_total: float | None, total: float, drop_pct: float = DEFAULT_DROP_PCT
) -> Literal["New", "Cheaper", ""]:
    if prev_total is None:
        return "New"
    if prev_total > 0 and (prev_total - total) / prev_total * 100 >= drop_pct - 1e-9:
        return "Cheaper"
    return ""


def change_for(
    prev: dict[tuple, float | None] | None,
    key: tuple,
    total: float | None,
    drop_pct: float = DEFAULT_DROP_PCT,
) -> str:
    """Blank when nothing was scored before, there is no total, or the key was only ever seen
    without a total."""
    if prev is None or total is None:
        return ""
    if key not in prev:
        return "New"
    if prev[key] is None:
        return ""
    return change(prev[key], total, drop_pct)

"""The current price of every flight, built from observations.

`observations` keeps one row per distinct price state of a flight (`origin|destination|date|cabin`).
`record_observations` adds to it after a scan; `rebuild_current` scores the newest state of every
fresh flight together and writes `current_offers`, the one table every page reads.
"""

from __future__ import annotations

import statistics
from bisect import bisect_right
from datetime import datetime, timedelta

from mmscan.config import Config
from mmscan.fares import FareSource
from mmscan.models import fees_eur
from mmscan.scoring import (
    CURRENT_COLUMNS,
    Scored,
    column_values,
    rank_key,
    score_rows,
    total_cost_eur,
)
from mmscan.store import Store

_CURRENT_BOOLS = (
    "fee_estimated",
    "expired",
    "route_good",
    "destination_good",
    "ceiling_good",
    "seats_ok",
    "direct",
    "chart_rate",
)

ALIVE_HOURS = 72  # a flight not seen for this long no longer counts as on offer in the history
LATEST = "SELECT * FROM observations WHERE id IN (SELECT max(id) FROM observations GROUP BY key)"
# The state before the latest one, for keys that have two or more.
PREVIOUS = (
    "SELECT * FROM observations WHERE id IN (SELECT max(id) FROM observations "
    "WHERE id NOT IN (SELECT max(id) FROM observations GROUP BY key) GROUP BY key)"
)


def flight_key(s: Scored, default_source: str = "lufthansa") -> str:
    """The default program keeps the original key, so history from before programs were stored
    still lines up; any other program's flights are separate keys with its id appended."""
    key = f"{s.origin}|{s.destination}|{s.date}|{s.cabin}"
    return key if s.source in (None, default_source) else f"{key}|{s.source}"


def _same_state(old, s: Scored) -> bool:
    """Did the price change? Compares the raw fee when both sides have it, so a new `usd_to_eur`
    rate does not make every flight look repriced."""
    if (
        old["miles"] != s.miles
        or bool(old["expired"]) != bool(s.expired)
        or bool(old["fee_estimated"]) != bool(s.fee_estimated)
    ):
        return False
    if old["fees_minor"] is not None and s.fees_minor is not None:
        return old["fees_minor"] == s.fees_minor and (old["currency"] or "") == (s.currency or "")
    if old["fees_eur"] is None or s.fees_eur is None:
        return old["fees_eur"] is None and s.fees_eur is None
    return round(old["fees_eur"], 2) == round(s.fees_eur, 2)


_DETAIL = (
    "availability_id",
    "source",
    "origin_region",
    "destination_region",
    "seats",
    "stops",
    "direct",
    "carriers",
    "flight_numbers",
    "departs_at",
    "arrives_at",
    "booking_link",
)
_STATE = ("miles", "fees_minor", "currency", "fees_eur", "fee_estimated", "expired")


def _detail_values(s: Scored) -> tuple:
    return tuple(int(v) if isinstance(v, bool) else v for v in (getattr(s, c) for c in _DETAIL))


def record_observations(
    store: Store, run_id: int, rows: list[Scored], now: datetime, default_source: str = "lufthansa"
) -> dict[str, int]:
    """Fold a run's scored rows into `observations`. A flight whose price state is unchanged gets
    `last_seen` (and its details) refreshed; a changed one gets a new row, or, when the run itself
    created the newest row, has that row replaced. Returns counts of new, changed and unchanged."""
    stamp = now.isoformat()
    latest = {r["key"]: r for r in store.conn.execute(LATEST).fetchall()}
    insert, touch, replace = [], [], []
    counts = {"new": 0, "changed": 0, "unchanged": 0}
    for s in rows:
        if s.miles is None or not s.date:
            continue
        key = flight_key(s, default_source)
        old = latest.get(key)
        if old is not None and _same_state(old, s):
            counts["unchanged"] += 1
            touch.append(
                (stamp, s.updated_at, *_detail_values(s), s.fees_minor, s.currency, old["id"])
            )
            continue
        counts["new" if old is None else "changed"] += 1
        values = (
            *_detail_values(s),
            s.miles,
            s.fees_minor,
            s.currency,
            s.fees_eur,
            int(s.fee_estimated),
            int(s.expired),
            s.updated_at,
        )
        if old is not None and old["run_id"] == run_id:
            replace.append((stamp, *values, old["id"]))
        else:
            insert.append(
                (key, run_id, stamp, stamp, s.origin, s.destination, s.date, s.cabin, *values)
            )
    detail_set = ", ".join(f"{c}=?" for c in _DETAIL)
    with store.conn:
        if touch:
            store.conn.executemany(
                f"UPDATE observations SET last_seen=?, source_updated_at=?, {detail_set}, "
                "fees_minor=COALESCE(?, fees_minor), currency=COALESCE(?, currency) WHERE id=?",
                touch,
            )
        if replace:
            state_set = ", ".join(f"{c}=?" for c in (*_STATE, "source_updated_at"))
            store.conn.executemany(
                f"UPDATE observations SET last_seen=?, {detail_set}, {state_set} WHERE id=?",
                replace,
            )
        if insert:
            cols = (
                "key, run_id, first_seen, last_seen, origin, destination, date, cabin, "
                + ", ".join(_DETAIL)
                + ", "
                + ", ".join((*_STATE, "source_updated_at"))
            )
            marks = ",".join("?" * (8 + len(_DETAIL) + len(_STATE) + 1))
            store.conn.executemany(f"INSERT INTO observations({cols}) VALUES ({marks})", insert)
    return counts


def _to_scored(r, cfg: Config) -> Scored:
    """An observation as an unscored row. Totals come from the raw fee and today's config."""
    if r["fees_minor"] is not None:
        fees = fees_eur(r["fees_minor"], r["currency"] or "", cfg.usd_to_eur)
        estimated = fees is None
    else:  # backfilled from an older results row: only the converted fee survives
        fees, estimated = r["fees_eur"], bool(r["fee_estimated"])
    miles = r["miles"]
    total = (
        None
        if fees is None or miles is None
        else total_cost_eur(miles, fees, cfg.mile_cents(r["source"]))
    )
    seats = r["seats"]
    return Scored(
        availability_id=r["availability_id"] or r["key"],
        cabin=r["cabin"],
        date=r["date"],
        origin=r["origin"],
        destination=r["destination"],
        origin_region=r["origin_region"],
        destination_region=r["destination_region"],
        miles=miles,
        fees_eur=fees,
        fee_estimated=estimated,
        total_eur=total,
        seats=seats,
        stops=r["stops"],
        carriers=r["carriers"],
        flight_numbers=r["flight_numbers"],
        departs_at=r["departs_at"],
        arrives_at=r["arrives_at"],
        booking_link=r["booking_link"],
        source=r["source"],
        updated_at=r["source_updated_at"],
        seats_ok=seats is None or seats >= cfg.min_seats,
        direct=None if r["direct"] is None else bool(r["direct"]),
        expired=bool(r["expired"]),
        fees_minor=r["fees_minor"],
        currency=r["currency"],
        first_seen=r["first_seen"],
        last_seen=r["last_seen"],
    )


def _total(r, cfg: Config) -> float | None:
    return _to_scored(r, cfg).total_eur


def fresh_observations(store: Store, cfg: Config, now: datetime) -> list:
    """Newest state of every flight seen within `relative.history_days`, not yet flown."""
    cutoff = (now - timedelta(days=cfg.relative.history_days)).isoformat()
    today = now.date().isoformat()
    return [
        r
        for r in store.conn.execute(LATEST).fetchall()
        if r["last_seen"] >= cutoff and (r["date"] or "") >= today
    ]


def _previous_totals(
    store: Store, cfg: Config, rows: list, run_id: int
) -> dict[tuple, float | None] | None:
    """What `diff.change_for` compares against: for a flight this run created or repriced, its
    total before; for every other flight, its own total (so it reads as unchanged). A flight with
    no earlier state is left out, which makes it New. None when nothing was observed before this
    run."""
    before = store.conn.execute(
        "SELECT 1 FROM observations WHERE run_id < ? LIMIT 1", (run_id,)
    ).fetchone()
    if before is None:
        return None
    previous = {r["key"]: r for r in store.conn.execute(PREVIOUS).fetchall()}
    prev: dict[tuple, float | None] = {}
    for r in rows:
        s_key = (r["origin"], r["destination"], r["date"], r["cabin"], r["source"])
        if r["run_id"] != run_id:
            prev[s_key] = _total(r, cfg)
        elif r["key"] in previous:
            prev[s_key] = _total(previous[r["key"]], cfg)
    return prev


def rebuild_current(
    store: Store,
    cfg: Config,
    run_id: int,
    now: datetime,
    fares: FareSource | None = None,
) -> list[Scored]:
    """Score every fresh flight together and replace `current_offers` with the result. The usual
    price of a route is the median over the dates currently on offer (across dates)."""
    rows = fresh_observations(store, cfg, now)
    current = [_to_scored(r, cfg) for r in rows]
    prev = _previous_totals(store, cfg, rows, run_id)
    scored = score_rows(current, [], cfg, fares, prev)
    keys = {s.key: flight_key(s, cfg.source) for s in scored}
    with store.conn:
        store.conn.execute("DELETE FROM current_offers")
        store.conn.executemany(
            f"INSERT INTO current_offers(key, {', '.join(CURRENT_COLUMNS)}) "
            f"VALUES (?{',?' * len(CURRENT_COLUMNS)})",
            [(keys[s.key], *column_values(s, CURRENT_COLUMNS)) for s in scored],
        )
    return scored


def ensure_current(
    store: Store, cfg: Config, now: datetime, fares: FareSource | None = None
) -> bool:
    """Fill `current_offers` from `observations` when it is empty, as after the migration that
    created them: the pages would otherwise show nothing until the next scan. Returns whether it
    rebuilt. Run id 0 means no flight counts as changed by this rebuild."""
    if store.conn.execute("SELECT 1 FROM current_offers LIMIT 1").fetchone():
        return False
    if store.conn.execute("SELECT 1 FROM observations LIMIT 1").fetchone() is None:
        return False
    rebuild_current(store, cfg, 0, now, fares)
    return True


def _from_current_row(r) -> Scored:
    values = {c: r[c] for c in CURRENT_COLUMNS}
    for c in _CURRENT_BOOLS:
        values[c] = None if values[c] is None else bool(values[c])
    return Scored(**values)


def load_current(store: Store) -> list[Scored]:
    """The scored current offers, best first. Pages read this; it takes no run id."""
    rows = store.conn.execute("SELECT * FROM current_offers").fetchall()
    return sorted((_from_current_row(r) for r in rows), key=rank_key)


def _priced_live(s: Scored) -> bool:
    return s.total_eur is not None and not s.expired and not s.fee_estimated


def legs_as_of(
    store: Store,
    cfg: Config,
    at: datetime,
    freshness_hours: int,
    before_run: int | None = None,
) -> list[Scored]:
    """Every priced, live flight as it stood at `at`: its newest state first seen by then, kept when
    it was seen within `freshness_hours` before. With `before_run`, states that run or a later one
    created are ignored, which gives the picture as it was before that run. Unscored; for trips,
    which only need prices."""
    return legs_history(store, cfg, [at], freshness_hours, before_run)[0]


def legs_history(
    store: Store,
    cfg: Config,
    moments: list[datetime],
    freshness_hours: int,
    before_run: int | None = None,
) -> list[list[Scored]]:
    """`legs_as_of` for several moments with one read of the table."""
    if not moments:
        return []
    window = timedelta(hours=freshness_hours)
    earliest = (min(moments) - window).isoformat()
    by_key: dict[str, list] = {}
    sql, args = "SELECT * FROM observations WHERE last_seen >= ?", [earliest]
    if before_run is not None:
        sql, args = sql + " AND run_id < ?", [*args, before_run]
    for r in store.conn.execute(sql + " ORDER BY key, id", args):
        by_key.setdefault(r["key"], []).append(r)
    out: list[list[Scored]] = []
    for at in moments:
        stamp, oldest = at.isoformat(), (at - window).isoformat()
        legs = []
        for rows in by_key.values():
            i = bisect_right([r["first_seen"] for r in rows], stamp) - 1
            if i < 0 or rows[i]["last_seen"] < oldest:
                continue
            s = _to_scored(rows[i], cfg)
            if _priced_live(s):
                legs.append(s)
        out.append(legs)
    return out


def route_points(
    store: Store,
    cfg: Config,
    origin: str,
    destination: str,
    cabin: str,
    now: datetime,
    days: int = 180,
) -> list[dict]:
    """The route's price over time, one point per day: the cheapest and median total across the
    dates that were on offer at the end of that day (the latest state of each by then)."""
    cutoff = (now - timedelta(days=days)).isoformat()
    by_key: dict[str, list] = {}
    for r in store.conn.execute(
        "SELECT * FROM observations WHERE origin=? AND destination=? AND cabin=? "
        "AND last_seen >= ? ORDER BY key, id",
        (origin, destination, cabin, cutoff),
    ):
        by_key.setdefault(r["key"], []).append((r, _total(r, cfg)))
    if not by_key:
        return []
    day = datetime.fromisoformat(min(rows[0][0]["first_seen"] for rows in by_key.values())).date()
    points = []
    while day <= now.date():
        end = min(datetime.combine(day, datetime.max.time(), tzinfo=now.tzinfo), now).isoformat()
        totals = []
        for rows in by_key.values():
            gone_after = (
                datetime.fromisoformat(rows[-1][0]["last_seen"]) + timedelta(hours=ALIVE_HOURS)
            ).isoformat()
            if not (rows[0][0]["first_seen"] <= end <= gone_after):
                continue  # not seen yet, or not seen for a while by then
            r, total = rows[bisect_right([x["first_seen"] for x, _ in rows], end) - 1]
            if total is not None and not r["expired"]:
                totals.append(total)
        if totals:
            points.append(
                {
                    "ts": end,
                    "low": min(totals),
                    "median": statistics.median(totals),
                    "n": len(totals),
                }
            )
        day += timedelta(days=1)
    return points

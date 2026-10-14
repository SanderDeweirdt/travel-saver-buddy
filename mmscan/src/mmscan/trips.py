"""Trip profiles: pair outbound and return legs into round trips, ranked by what the whole trip
costs the whole party. Pure over stored results; no API calls."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from mmscan.config import Config, TripProfile
from mmscan.report import _age_hours, scored_from_row
from mmscan.scoring import Scored
from mmscan.store import Store

MAX_PAIRS = 200  # kept per trip after ranking


@dataclass
class TripPair:
    trip: str
    out: Scored
    back: Scored | None
    seats: int
    budget: float | None = None

    @property
    def cabin(self) -> str:
        return self.out.cabin

    @property
    def legs(self) -> list[Scored]:
        return [self.out] + ([self.back] if self.back else [])

    @property
    def miles_pp(self) -> int:
        return sum(s.miles or 0 for s in self.legs)

    @property
    def fees_pp(self) -> float:
        return round(sum(s.fees_eur or 0 for s in self.legs), 2)

    @property
    def total_pp(self) -> float:
        return round(sum(s.total_eur or 0 for s in self.legs), 2)

    @property
    def party_total(self) -> float:
        return round(self.total_pp * self.seats, 2)

    @property
    def stay_days(self) -> int | None:
        if not self.back:
            return None
        return (date.fromisoformat(self.back.date) - date.fromisoformat(self.out.date)).days

    @property
    def within_budget(self) -> bool | None:
        return None if self.budget is None else self.party_total <= self.budget

    @property
    def key(self) -> tuple:
        return tuple(s.key for s in self.legs)


@dataclass
class TripView:
    profile: TripProfile
    seats: int
    cabins: list[str]
    pairs: list[TripPair] = field(default_factory=list)
    n_pairs: int = 0
    n_within_budget: int = 0
    n_out: int = 0
    n_back: int = 0
    note: str = ""
    by_day: dict[str, float] = field(default_factory=dict)  # departure date -> cheapest party total

    @property
    def best(self) -> TripPair | None:
        return self.pairs[0] if self.pairs else None


def latest_legs(
    store: Store,
    cfg: Config,
    now: datetime,
    max_run_id: int | None = None,
) -> list[Scored]:
    """Newest observation of every priced, live result seen within trip_freshness_hours of
    `now`. `max_run_id` rebuilds the picture as it was before a given run."""
    cutoff = (now - timedelta(hours=cfg.trip_freshness_hours)).isoformat()
    sql = (
        "SELECT r.* FROM results r JOIN runs u ON u.id = r.run_id "
        "WHERE u.started_at >= ? AND r.total_eur IS NOT NULL AND r.expired = 0 "
        "AND r.fee_estimated = 0"
    )
    args: list = [cutoff]
    if max_run_id is not None:
        sql += " AND r.run_id <= ?"
        args.append(max_run_id)
    latest: dict[tuple, Scored] = {}
    for r in store.conn.execute(sql + " ORDER BY r.run_id", args).fetchall():
        s = scored_from_row(r)
        latest[s.key] = s
    return list(latest.values())


def _in(window, d: str | None) -> bool:
    if not d:
        return False
    try:
        return window.start <= date.fromisoformat(d) <= window.end
    except ValueError:
        return False


def leg_ok(s: Scored, trip: TripProfile, cfg: Config) -> bool:
    if s.cabin not in cfg.trip_cabins(trip):
        return False
    need = cfg.trip_seats(trip)
    if s.seats is not None and s.seats < need:
        return False
    if trip.max_stops is not None:
        stops = 0 if s.stops is None and s.direct else s.stops
        if stops is not None and stops > trip.max_stops:
            return False
    return True


def build_trip(legs: list[Scored], trip: TripProfile, cfg: Config) -> TripView:
    seats = cfg.trip_seats(trip)
    view = TripView(trip, seats, cfg.trip_cabins(trip))
    outs = [
        s
        for s in legs
        if s.origin in trip.origins
        and s.destination in trip.destinations
        and _in(trip.depart, s.date)
        and leg_ok(s, trip, cfg)
    ]
    view.n_out = len(outs)
    if not trip.round_trip:
        pairs = [TripPair(trip.name, o, None, seats, trip.max_total_eur) for o in outs]
    else:
        backs = [
            s
            for s in legs
            if s.origin in trip.destinations
            and s.destination in trip.origins
            and _in(trip.return_window, s.date)
            and leg_ok(s, trip, cfg)
        ]
        view.n_back = len(backs)
        by_cabin: dict[str, list[Scored]] = {}
        for b in backs:
            by_cabin.setdefault(b.cabin, []).append(b)
        pairs = []
        for o in outs:
            od = date.fromisoformat(o.date)
            for b in by_cabin.get(o.cabin, []):
                if not trip.open_jaw and (b.origin != o.destination or b.destination != o.origin):
                    continue
                stay = (date.fromisoformat(b.date) - od).days
                if stay < 0:
                    continue
                if trip.stay_days and not trip.stay_days.min <= stay <= trip.stay_days.max:
                    continue
                pairs.append(TripPair(trip.name, o, b, seats, trip.max_total_eur))
    pairs.sort(key=lambda p: (p.party_total, p.out.date, p.key))
    for p in pairs:  # pairs are sorted, so the first one seen for a day is its cheapest
        view.by_day.setdefault(p.out.date, p.party_total)
    view.n_pairs = len(pairs)
    view.n_within_budget = sum(1 for p in pairs if p.within_budget)
    view.pairs = pairs[:MAX_PAIRS]
    view.note = _note(view)
    return view


def _note(v: TripView) -> str:
    """Why a trip has nothing to show, in words you can act on."""
    if v.pairs:
        return ""
    if v.n_out == 0:
        return (
            "No outbound availability found yet for these airports, dates, cabins and "
            f"{v.seats} seat(s). The next scan may find some."
        )
    if v.profile.round_trip and v.n_back == 0:
        return f"{v.n_out} outbound option(s) found, but nothing on the return side yet."
    return (
        f"{v.n_out} outbound and {v.n_back} return option(s) found, but none fit the stay length "
        "or airports together."
    )


def calendar_cells(view: TripView) -> dict:
    """Cheapest whole-party price per departure day over the trip's departure window, as a grid
    that starts on a Monday. `level` runs from 0 (cheapest fifth) to 4; None means no seats."""
    w = view.profile.depart
    days = [w.start + timedelta(days=i) for i in range((w.end - w.start).days + 1)]
    prices = [view.by_day[d.isoformat()] for d in days if d.isoformat() in view.by_day]
    lo, hi = (min(prices), max(prices)) if prices else (0.0, 0.0)
    cells = []
    for d in days:
        total = view.by_day.get(d.isoformat())
        level = None if total is None else min(4, int((total - lo) / (hi - lo + 0.01) * 5))
        cells.append({"date": d, "total": total, "level": level, "best": total == lo and prices})
    return {"cells": cells, "lead": w.start.weekday(), "low": lo, "high": hi}


def trip_trend(store: Store, cfg: Config, trip: TripProfile, now: datetime, days: int = 30):
    """Best whole-party price of a trip as it stood at the end of each day, from the stored runs.
    One point per day (the day's last run), oldest first; days with no option are left out."""
    cutoff = (now - timedelta(days=days)).isoformat()
    rows = store.conn.execute(
        "SELECT id, started_at FROM runs WHERE started_at >= ? ORDER BY id", (cutoff,)
    ).fetchall()
    last_of_day: dict[str, tuple[int, str]] = {}
    for r in rows:
        last_of_day[r["started_at"][:10]] = (r["id"], r["started_at"])
    out = []
    for day, (run_id, started) in sorted(last_of_day.items()):
        legs = latest_legs(store, cfg, datetime.fromisoformat(started), max_run_id=run_id)
        best = build_trip(legs, trip, cfg).best
        if best:
            out.append({"day": day, "total": best.party_total})
    return out


def trip_views(store: Store, cfg: Config, now: datetime) -> list[TripView]:
    legs = latest_legs(store, cfg, now)
    return [build_trip(legs, t, cfg) for t in cfg.trips]


def age_hours(pair: TripPair, now: datetime) -> float | None:
    ages = [_age_hours(s.updated_at, now) for s in pair.legs]
    ages = [a for a in ages if a is not None]
    return max(ages) if ages else None


STALE_HOURS = 48


def alertable(pair: TripPair, cfg: Config, now: datetime) -> bool:
    """No alert on stale data, nor (unless notify.unverified) on dynamic-carrier prices."""
    age = age_hours(pair, now)
    if age is not None and age > STALE_HOURS:
        return False
    if not cfg.notify.unverified:
        return all(cfg.pricing_model(s.carriers) == "fixed" for s in pair.legs)
    return True


@dataclass
class TripAlert:
    pair: TripPair
    change: str  # New | Cheaper
    was: float | None = None


def trip_alerts(store: Store, cfg: Config, run_id: int, now: datetime) -> list[TripAlert]:
    """Top pairs of each trip that are new, or at least drops.min_pct cheaper than when they
    were last seen before this run. Nothing on the first run: there is nothing to compare."""
    if not cfg.trips:
        return []
    run = store.run_info(run_id)
    if run is None:
        return []
    started = datetime.fromisoformat(run["started_at"])
    before = latest_legs(store, cfg, started, max_run_id=run_id - 1)
    if not before:
        return []
    now_legs = latest_legs(store, cfg, now, max_run_id=run_id)
    out = []
    for trip in cfg.trips:
        prev = {p.key: p.party_total for p in build_trip(before, trip, cfg).pairs}
        cur = build_trip(now_legs, trip, cfg)
        top = [p for p in cur.pairs if p.within_budget is not False and alertable(p, cfg, now)][
            : trip.alert_top
        ]
        for p in top:
            was = prev.get(p.key)
            if was is None:
                out.append(TripAlert(p, "New"))
            elif p.party_total <= was * (1 - cfg.drops.min_pct / 100):
                out.append(TripAlert(p, "Cheaper", was))
    return out

"""Step 5: total cost, baselines, flags and verdicts. Pure over stored rows; no API calls."""

from __future__ import annotations

import json
import logging
import statistics
from dataclasses import astuple, dataclass, fields
from datetime import datetime, timedelta

from mmscan.config import Config
from mmscan.diff import change_for, previous_totals
from mmscan.fares import FareSource, NoFares, value_band
from mmscan.models import Trip, fees_eur, parse_cabin_offers
from mmscan.store import Store

log = logging.getLogger("mmscan.scoring")

DEAL = "Deal"
WORTH = "Worth a look"
SKIP = "Skip"
VERDICT_ORDER = {DEAL: 0, WORTH: 1, SKIP: 2}
CHART_RATE_SHARE = 0.95


def percentile(values: list[float], p: float) -> float | None:
    """Linear interpolation between closest ranks (numpy's default). None when empty."""
    if not values:
        return None
    xs = sorted(values)
    pos = (len(xs) - 1) * p / 100
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def percentile_rank(values: list[float], x: float) -> float | None:
    """Mid-rank position of x in values, 0 to 100 (builder call 6)."""
    if not values:
        return None
    below = sum(1 for v in values if v < x)
    equal = sum(1 for v in values if v == x)
    return (below + 0.5 * equal) / len(values) * 100


def total_cost_eur(miles: int, fees: float, cents: float) -> float:
    return round(miles * cents / 100 + fees, 2)


def pick_trip(
    trips: list[Trip], cabin: str, min_seats: int, cents: float
) -> tuple[Trip, bool] | None:
    """Cheapest priced trip in the cabin that meets min_seats (unknown seats count as meeting,
    builder call 4); otherwise the cheapest priced one with seats_ok False."""
    priced = [
        t
        for t in trips
        if t.cabin == cabin and t.miles > 0 and fees_eur(t.taxes_minor, t.currency) is not None
    ]
    if not priced:
        return None

    def key(t: Trip) -> tuple:
        return (total_cost_eur(t.miles, fees_eur(t.taxes_minor, t.currency), cents), t.stops, t.id)

    meets = [t for t in priced if t.seats is None or t.seats >= min_seats]
    if meets:
        return min(meets, key=key), True
    return min(priced, key=key), False


def verdict(route_good: bool, destination_good: bool, seats_ok: bool, capped: bool = False) -> str:
    """`capped`: a layer had thin data and no benchmark, so the best reachable is Worth a look."""
    if route_good and destination_good:
        return WORTH if capped or not seats_ok else DEAL
    if route_good or destination_good:
        return WORTH
    return SKIP


@dataclass
class Scored:
    availability_id: str
    cabin: str
    date: str | None
    origin: str | None
    destination: str | None
    origin_region: str | None
    destination_region: str | None
    miles: int | None
    fees_eur: float | None
    fee_estimated: bool
    total_eur: float | None
    seats: int | None
    stops: int | None
    carriers: str | None
    flight_numbers: str | None
    departs_at: str | None
    arrives_at: str | None
    booking_link: str | None
    updated_at: str | None
    route_good: bool | None = None
    destination_good: bool | None = None
    ceiling_good: bool | None = None
    seats_ok: bool | None = None
    direct: bool | None = None
    chart_rate: bool | None = None
    route_pct: float | None = None
    destination_pct: float | None = None
    verdict: str = SKIP
    cash_fare_eur: float | None = None
    saving_eur: float | None = None
    value_cents: float | None = None
    value_band: str | None = None
    change: str = ""
    expired: bool = False

    @property
    def key(self) -> tuple:
        return (self.origin, self.destination, self.date, self.cabin)


SCORED_COLUMNS = [f.name for f in fields(Scored)]


def rank_key(s: Scored) -> tuple:
    total = s.total_eur if s.total_eur is not None else float("inf")
    return (VERDICT_ORDER.get(s.verdict, 3), total, not s.direct)


def _offer_row(avail: dict, row, cabin: str, offer, trips, link, cfg: Config) -> Scored:
    route = avail.get("Route") or {}
    base = dict(
        availability_id=row["id"],
        cabin=cabin,
        date=avail.get("Date"),
        origin=route.get("OriginAirport"),
        destination=route.get("DestinationAirport"),
        origin_region=route.get("OriginRegion"),
        destination_region=route.get("DestinationRegion"),
        updated_at=row["updated_at"],
        booking_link=link,
    )
    picked = pick_trip(trips, cabin, cfg.min_seats, cfg.mile_cost_eur_cents)
    if picked:
        trip, seats_ok = picked
        fees = fees_eur(trip.taxes_minor, trip.currency)
        return Scored(
            **base,
            miles=trip.miles,
            fees_eur=fees,
            fee_estimated=False,
            total_eur=total_cost_eur(trip.miles, fees, cfg.mile_cost_eur_cents),
            seats=trip.seats,
            stops=trip.stops,
            carriers=trip.carriers,
            flight_numbers=trip.flight_numbers,
            departs_at=trip.departs_at,
            arrives_at=trip.arrives_at,
            seats_ok=seats_ok,
            direct=trip.stops == 0,
        )
    return Scored(
        **base,
        miles=offer.miles,
        fees_eur=None,
        fee_estimated=True,
        total_eur=None,
        seats=offer.seats,
        stops=None,
        carriers=offer.airlines,
        flight_numbers=None,
        departs_at=None,
        arrives_at=None,
        seats_ok=offer.seats is None or offer.seats >= cfg.min_seats,
        direct=offer.direct,
    )


def _trip_from_row(r) -> Trip:
    return Trip(
        id=r["id"],
        availability_id=r["availability_id"],
        cabin=r["cabin"],
        miles=r["mileage_cost"] or 0,
        taxes_minor=r["total_taxes"] or 0,
        currency=r["taxes_currency"] or "",
        seats=r["remaining_seats"],
        stops=r["stops"] or 0,
        carriers=r["carriers"] or "",
        flight_numbers=r["flight_numbers"] or "",
        departs_at=r["departs_at"] or "",
        arrives_at=r["arrives_at"] or "",
        total_duration=r["total_duration"],
        raw={},
    )


def current_rows(store: Store, cfg: Config, run_id: int) -> tuple[list[Scored], list[str]]:
    """One row per availability and configured cabin, priced from stored trips when present."""
    out: list[Scored] = []
    warnings: list[str] = []
    empty_currency = 0
    for row in store.conn.execute(
        "SELECT id, updated_at, raw_json FROM availabilities WHERE run_id=? ORDER BY id", (run_id,)
    ).fetchall():
        avail = json.loads(row["raw_json"])
        updated = row["updated_at"] or ""
        fetch = store.conn.execute(
            "SELECT status, booking_link FROM trip_fetches "
            "WHERE availability_id=? AND updated_at=?",
            (row["id"], updated),
        ).fetchone()
        trips = [
            _trip_from_row(r)
            for r in store.conn.execute(
                "SELECT * FROM trips WHERE availability_id=? AND updated_at=?", (row["id"], updated)
            )
        ]
        for t in trips:
            if t.currency == "":
                empty_currency += 1
            elif t.currency != "EUR":
                warnings.append(
                    f"trip {t.id}: taxes in {t.currency!r}, not EUR; left unpriced (builder call 3)"
                )
        link = fetch["booking_link"] if fetch else None
        for offer in parse_cabin_offers(avail, cfg.cabins):
            s = _offer_row(avail, row, offer.cabin, offer, trips, link, cfg)
            if fetch is not None and fetch["status"] == "expired":
                s.expired = True
            out.append(s)
    if empty_currency:
        warnings.append(
            f"{empty_currency} trips had an empty TaxesCurrency; their taxes were read as EUR"
        )
    return out, warnings


def history_rows(store: Store, cfg: Config, run_id: int, now: datetime) -> list[Scored]:
    cutoff = (now - timedelta(days=cfg.relative.history_days)).isoformat()
    rows = store.conn.execute(
        "SELECT r.* FROM results r JOIN runs u ON u.id = r.run_id "
        "WHERE r.run_id != ? AND u.started_at >= ? AND r.total_eur IS NOT NULL AND r.expired = 0 "
        "ORDER BY r.run_id",
        (run_id, cutoff),
    ).fetchall()
    out = []
    for r in rows:
        values = {c: r[c] for c in SCORED_COLUMNS}
        for c in ("fee_estimated", "expired"):
            values[c] = bool(values[c])
        out.append(Scored(**values))
    return out


def _group(samples: list[Scored], key) -> dict[tuple, list[float]]:
    out: dict[tuple, list[float]] = {}
    for s in samples:
        if s.total_eur is not None:
            out.setdefault(key(s), []).append(s.total_eur)
    return out


def _route(s: Scored) -> tuple:
    return (s.origin, s.destination, s.cabin)


def _dest(s: Scored) -> tuple:
    return (s.origin_region, s.destination, s.cabin)


def score_rows(
    current: list[Scored],
    history: list[Scored],
    cfg: Config,
    fares: FareSource | None = None,
    prev: dict[tuple, float | None] | None = None,
) -> list[Scored]:
    fares = fares or NoFares()
    cents = cfg.mile_cost_eur_cents
    live = [s for s in current if not s.expired]

    # Latest observation per (origin, destination, date, cabin) wins (builder call 7).
    latest: dict[tuple, Scored] = {s.key: s for s in history}
    latest.update({s.key: s for s in live})

    # Fee estimate: median actual fee of the same route and cabin (builder call 8).
    actual: dict[tuple, list[float]] = {}
    for s in latest.values():
        if not s.fee_estimated and s.fees_eur is not None:
            actual.setdefault(_route(s), []).append(s.fees_eur)
    for s in live:
        if s.fee_estimated:
            fees = actual.get(_route(s))
            if fees:
                s.fees_eur = round(statistics.median(fees), 2)
                s.total_eur = total_cost_eur(s.miles, s.fees_eur, cents)

    samples = list(latest.values())
    by_route = _group(samples, _route)
    by_dest = _group(samples, _dest)
    pg = cfg.relative.percentile_good
    n_min = cfg.relative.min_samples

    for s in current:
        if s.expired or s.total_eur is None:
            s.verdict = SKIP
            continue
        bm = cfg.benchmark_for(
            s.cabin, s.origin, s.origin_region, s.destination, s.destination_region
        )
        if bm:
            s.ceiling_good = s.miles <= bm.good_miles_max and s.fees_eur <= bm.fees_max_eur
            s.chart_rate = s.miles >= CHART_RATE_SHARE * bm.chart_rate_miles
        capped = False
        layers = []
        for values in (by_route.get(_route(s), []), by_dest.get(_dest(s), [])):
            if len(values) >= n_min:
                layers.append(s.total_eur <= percentile(values, pg))
            elif bm:
                layers.append(bool(s.ceiling_good))
            else:
                layers.append(False)
                capped = True
        s.route_good, s.destination_good = layers
        s.route_pct = percentile_rank(by_route.get(_route(s), []), s.total_eur)
        s.destination_pct = percentile_rank(by_dest.get(_dest(s), []), s.total_eur)
        s.verdict = verdict(s.route_good, s.destination_good, bool(s.seats_ok), capped)

        if s.date and s.origin and s.destination:
            cash = fares.fare(s.origin, s.destination, s.cabin, s.date[:7])
            if cash is not None:
                s.cash_fare_eur = cash
                s.saving_eur = round(cash - s.total_eur, 2)
                s.value_cents = (cash - s.fees_eur) / s.miles * 100
                s.value_band = value_band(s.value_cents, cfg)
        s.change = change_for(prev, s.key, s.total_eur)
    return sorted(current, key=rank_key)


def score_run(
    store: Store,
    cfg: Config,
    run_id: int,
    now: datetime,
    fares: FareSource | None = None,
) -> tuple[list[Scored], list[str]]:
    """Score every result of the run and write the `results` table. Returns (rows, warnings)."""
    current, warnings = current_rows(store, cfg, run_id)
    history = history_rows(store, cfg, run_id, now)
    prev = previous_totals(store, run_id)
    scored = score_rows(current, history, cfg, fares, prev)
    warnings += list(getattr(fares, "warnings", []) or [])
    placeholders = ",".join("?" * (len(SCORED_COLUMNS) + 1))
    with store.conn:
        store.conn.execute("DELETE FROM results WHERE run_id=?", (run_id,))
        store.conn.executemany(
            f"INSERT INTO results(run_id, {', '.join(SCORED_COLUMNS)}) VALUES ({placeholders})",
            [(run_id, *astuple(s)) for s in scored],
        )
    return scored, warnings

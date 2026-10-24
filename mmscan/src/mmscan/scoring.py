"""Step 5: total cost, baselines, flags and verdicts. Pure over stored rows; no API calls."""

from __future__ import annotations

import json
import logging
import statistics
from bisect import bisect_left, bisect_right
from dataclasses import dataclass, fields
from datetime import UTC, datetime

from mmscan.config import Config
from mmscan.diff import change_for
from mmscan.fares import FareSource, NoFares, value_band
from mmscan.models import CABIN_PREFIX, Trip, fees_eur, parse_cabin_offers
from mmscan.store import Store

log = logging.getLogger("mmscan.scoring")

DEAL = "Deal"
WORTH = "Worth a look"
SKIP = "Skip"
USD_RATE_MAX_AGE_DAYS = 30
UNRANKED = "Unranked"  # dynamic fare with too little observed history to judge
VERDICT_ORDER = {DEAL: 0, WORTH: 1, SKIP: 2, UNRANKED: 3}
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


def percentile_rank_sorted(xs: list[float], x: float) -> float | None:
    """`percentile_rank` over an already sorted list, in O(log n)."""
    if not xs:
        return None
    below = bisect_left(xs, x)
    equal = bisect_right(xs, x) - below
    return (below + 0.5 * equal) / len(xs) * 100


def total_cost_eur(miles: int, fees: float, cents: float) -> float:
    return round(miles * cents / 100 + fees, 2)


def pick_trip(
    trips: list[Trip], cabin: str, min_seats: int, cents: float, usd_to_eur: float | None = None
) -> tuple[Trip, bool] | None:
    """Cheapest priced trip in the cabin that meets min_seats (unknown seats count as meeting,
    builder call 4); otherwise the cheapest priced one with seats_ok False."""
    priced = [
        t
        for t in trips
        if t.cabin == cabin
        and t.miles > 0
        and fees_eur(t.taxes_minor, t.currency, usd_to_eur) is not None
    ]
    if not priced:
        return None

    def key(t: Trip) -> tuple:
        fee = fees_eur(t.taxes_minor, t.currency, usd_to_eur)
        return (total_cost_eur(t.miles, fee, cents), t.stops, t.id)

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
    source: str | None = None  # seats.aero program; None on rows from before programs were stored
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
    # Not in `results`: the raw fee as the API gave it (observations keep it), and when we first and
    # last saw this price (current_offers keeps them).
    fees_minor: int | None = None
    currency: str | None = None
    first_seen: str | None = None
    last_seen: str | None = None

    @property
    def key(self) -> tuple:
        return (self.origin, self.destination, self.date, self.cabin, self.source)


TRANSIENT = ("fees_minor", "currency", "first_seen", "last_seen")
SCORED_COLUMNS = [f.name for f in fields(Scored) if f.name not in TRANSIENT]
CURRENT_COLUMNS = SCORED_COLUMNS + ["first_seen", "last_seen"]


def column_values(s: Scored, columns: list[str]) -> tuple:
    return tuple(getattr(s, c) for c in columns)


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
        source=row["source"] or avail.get("Source"),
    )
    cents = cfg.mile_cents(base["source"])
    picked = pick_trip(trips, cabin, cfg.min_seats, cents, cfg.usd_to_eur)
    if picked:
        trip, seats_ok = picked
        fees = fees_eur(trip.taxes_minor, trip.currency, cfg.usd_to_eur)
        return Scored(
            **base,
            miles=trip.miles,
            fees_eur=fees,
            fee_estimated=False,
            total_eur=total_cost_eur(trip.miles, fees, cents),
            seats=trip.seats,
            stops=trip.stops,
            carriers=trip.carriers,
            flight_numbers=trip.flight_numbers,
            departs_at=trip.departs_at,
            arrives_at=trip.arrives_at,
            seats_ok=seats_ok,
            direct=trip.stops == 0,
            fees_minor=trip.taxes_minor,
            currency=trip.currency,
        )
    # No trip details: the summary carries the cheapest trip's taxes per cabin (live finding).
    taxes = avail.get(f"{CABIN_PREFIX[cabin]}TotalTaxes")
    fees = None
    minor, currency = None, None
    if isinstance(taxes, int) and not isinstance(taxes, bool) and taxes > 0:
        minor, currency = taxes, avail.get("TaxesCurrency") or ""
        fees = fees_eur(taxes, currency, cfg.usd_to_eur)
    priced = fees is not None
    return Scored(
        **base,
        miles=offer.miles,
        fees_eur=fees,
        fee_estimated=not priced,
        total_eur=total_cost_eur(offer.miles, fees, cents) if priced else None,
        seats=offer.seats,
        stops=None,
        carriers=offer.airlines,
        flight_numbers=None,
        departs_at=None,
        arrives_at=None,
        seats_ok=offer.seats is None or offer.seats >= cfg.min_seats,
        direct=offer.direct,
        fees_minor=minor,
        currency=currency,
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


def _currency_warnings(currencies: dict[str, int], cfg: Config) -> list[str]:
    out = []
    if currencies.get(""):
        out.append(f"{currencies['']} objects had an empty TaxesCurrency; taxes were read as EUR")
    if currencies.get("USD"):
        if cfg.usd_to_eur:
            out.append(
                f"{currencies['USD']} objects report fees in USD; converted at usd_to_eur="
                f"{cfg.usd_to_eur}"
            )
            age = cfg.usd_rate_age_days(datetime.now(UTC).date())
            if age is not None and age > USD_RATE_MAX_AGE_DAYS:
                out.append(
                    f"usd_to_eur was last checked {age} days ago (over {USD_RATE_MAX_AGE_DAYS}); "
                    f"update it and usd_to_eur_date in config.yaml"
                )
        else:
            out.append(
                f"{currencies['USD']} objects report fees in USD and usd_to_eur is not set; "
                f"they are unpriced"
            )
    for cur, n in sorted(currencies.items()):
        if cur not in ("", "EUR", "USD"):
            out.append(f"{n} objects report fees in {cur}; they are unpriced")
    return out


def current_rows(store: Store, cfg: Config, run_id: int) -> tuple[list[Scored], list[str]]:
    """One row per availability and configured cabin, priced from stored trips when present."""
    out: list[Scored] = []
    warnings: list[str] = []
    currencies: dict[str, int] = {}
    for row in store.conn.execute(
        "SELECT id, updated_at, source, raw_json FROM availabilities WHERE run_id=? ORDER BY id",
        (run_id,),
    ).fetchall():
        avail = json.loads(row["raw_json"])
        if avail.get("TaxesCurrency") is not None:
            cur = avail["TaxesCurrency"]
            currencies[cur] = currencies.get(cur, 0) + 1
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
            currencies[t.currency] = currencies.get(t.currency, 0) + 1
        link = fetch["booking_link"] if fetch else None
        for offer in parse_cabin_offers(avail, cfg.cabins):
            s = _offer_row(avail, row, offer.cabin, offer, trips, link, cfg)
            if fetch is not None and fetch["status"] == "expired":
                s.expired = True
            out.append(s)
    warnings += _currency_warnings(currencies, cfg)
    return out, warnings


def _group(samples: list[Scored], key) -> dict[tuple, list[float]]:
    out: dict[tuple, list[float]] = {}
    for s in samples:
        if s.total_eur is not None:
            out.setdefault(key(s), []).append(s.total_eur)
    return out


def _route(s: Scored) -> tuple:
    return (s.origin, s.destination, s.cabin, s.source)


def _dest(s: Scored) -> tuple:
    return (s.origin_region, s.destination, s.cabin, s.source)


def score_rows(
    current: list[Scored],
    history: list[Scored],
    cfg: Config,
    fares: FareSource | None = None,
    prev: dict[tuple, float | None] | None = None,
) -> list[Scored]:
    fares = fares or NoFares()
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
                s.total_eur = total_cost_eur(s.miles, s.fees_eur, cfg.mile_cents(s.source))

    samples = list(latest.values())
    by_route = {k: sorted(v) for k, v in _group(samples, _route).items()}
    by_dest = {k: sorted(v) for k, v in _group(samples, _dest).items()}
    cuts: dict[tuple, float] = {}  # one threshold per group, not one per row
    pg = cfg.relative.percentile_good
    n_min = cfg.relative.min_samples
    disc = cfg.relative.min_discount_pct / 100

    for s in current:
        if s.expired or s.total_eur is None:
            s.verdict = SKIP
            continue
        bm = cfg.benchmark_for(
            s.cabin, s.origin, s.origin_region, s.destination, s.destination_region
        )
        model = cfg.pricing_model(s.carriers)
        fixed = model == "fixed"
        if bm:
            s.chart_rate = s.miles >= CHART_RATE_SHARE * bm.chart_rate_miles
            # The chart saver level only means something on fixed-chart carriers.
            if fixed:
                s.ceiling_good = s.miles <= bm.chart_rate_miles and s.fees_eur <= bm.fees_max_eur
        capped = False
        thin = 0
        layers = []
        for layer, gkey, values in (
            ("route", _route(s), by_route.get(_route(s), [])),
            ("dest", _dest(s), by_dest.get(_dest(s), [])),
        ):
            if len(values) >= n_min:
                ck = (layer, gkey)
                if ck not in cuts:
                    cuts[ck] = min(percentile(values, pg), percentile(values, 50) * (1 - disc))
                layers.append(s.total_eur <= cuts[ck])
            else:
                thin += 1
                if fixed and bm:
                    layers.append(bool(s.ceiling_good))  # chart saver stands in for history
                else:
                    layers.append(False)
                    capped = True
        s.route_good, s.destination_good = layers
        s.route_pct = percentile_rank_sorted(by_route.get(_route(s), []), s.total_eur)
        s.destination_pct = percentile_rank_sorted(by_dest.get(_dest(s), []), s.total_eur)
        s.verdict = verdict(s.route_good, s.destination_good, bool(s.seats_ok), capped)
        if fixed and cfg.deals.by_ceiling and s.ceiling_good and s.seats_ok:
            s.verdict = DEAL
        elif not fixed and thin == 2:
            s.verdict = UNRANKED

        if s.date and s.origin and s.destination:
            cash = fares.fare(s.origin, s.destination, s.cabin, s.date[:7])
            if cash is not None:
                s.cash_fare_eur = cash
                s.saving_eur = round(cash - s.total_eur, 2)
                s.value_cents = (cash - s.fees_eur) / s.miles * 100
                s.value_band = value_band(s.value_cents, cfg)
        s.change = change_for(prev, s.key, s.total_eur, cfg.drops.min_pct)
    return sorted(current, key=rank_key)


def score_run(
    store: Store,
    cfg: Config,
    run_id: int,
    now: datetime,
    fares: FareSource | None = None,
) -> tuple[list[Scored], list[str]]:
    """Fold the run into `observations`, then score every fresh flight together and rebuild
    `current_offers`. Returns (the current offers, warnings)."""
    from mmscan.offers import rebuild_current, record_observations

    current, warnings = current_rows(store, cfg, run_id)
    record_observations(store, run_id, current, now, cfg.source)
    scored = rebuild_current(store, cfg, run_id, now, fares)
    warnings += list(getattr(fares, "warnings", []) or [])
    return scored, warnings

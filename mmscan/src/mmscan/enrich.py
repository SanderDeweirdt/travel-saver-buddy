"""Steps 3 and 4: pre-screen region results on miles, then fetch trips (fees) for candidates."""

from __future__ import annotations

import json
import logging
import statistics
from dataclasses import dataclass

from mmscan.client import CapReached, Client, NotFound
from mmscan.config import Config
from mmscan.models import fees_eur, parse_cabin_offers, parse_trip
from mmscan.scoring import percentile
from mmscan.store import Store

log = logging.getLogger("mmscan.enrich")


@dataclass
class EnrichStats:
    called: int = 0
    priced: int = 0
    expired: int = 0
    skipped_cached: int = 0
    left_over: int = 0
    cap_reached: bool = False


def _region_rows(store: Store, run_id: int) -> list:
    return store.conn.execute(
        "SELECT id, origin, destination, origin_region, updated_at, raw_json FROM availabilities "
        "WHERE run_id=? AND origin_kind='region' ORDER BY id",
        (run_id,),
    ).fetchall()


def count_cached(store: Store, run_id: int) -> int:
    return sum(
        1 for r in _region_rows(store, run_id) if store.has_fetch(r["id"], r["updated_at"] or "")
    )


def select_candidates(store: Store, cfg: Config, run_id: int) -> list[str]:
    """Region availabilities in the cheapest `prescreen.percentile` of their route group or their
    destination group, in any configured cabin (builder call 9), cheapest first. Availabilities
    whose trips are already stored for their current UpdatedAt are not candidates."""
    rows = [
        r
        for r in _region_rows(store, run_id)
        if not store.has_fetch(r["id"], r["updated_at"] or "")
    ]
    best: dict[str, int] = {}
    for cabin in cfg.cabins:
        offers = []
        for r in rows:
            for o in parse_cabin_offers(json.loads(r["raw_json"]), [cabin]):
                offers.append((r, o.miles))
        groups: dict[tuple, list[int]] = {}
        for r, miles in offers:
            groups.setdefault(("route", r["origin"], r["destination"]), []).append(miles)
            groups.setdefault(("dest", r["origin_region"], r["destination"]), []).append(miles)
        cut = {k: percentile(v, cfg.prescreen.percentile) for k, v in groups.items()}
        for r, miles in offers:
            route_ok = miles <= cut[("route", r["origin"], r["destination"])]
            dest_ok = miles <= cut[("dest", r["origin_region"], r["destination"])]
            if route_ok or dest_ok:
                best[r["id"]] = min(miles, best.get(r["id"], miles))
    return sorted(best, key=lambda i: (best[i], i))


def _primary_link(body) -> str | None:
    links = body.get("booking_links") if isinstance(body, dict) else None
    if not links:
        return None
    primary = [lk for lk in links if lk.get("primary")]
    return (primary or links)[0].get("link")


def enrich(
    client: Client, store: Store, cfg: Config, run_id: int, candidates: list[str]
) -> EnrichStats:
    """Get Trips for up to `enrich.max_calls` candidates. Each result is committed as it arrives,
    so a crash or Ctrl-C does not pay for it again."""
    stats = EnrichStats(skipped_cached=count_cached(store, run_id))
    updated = {r["id"]: r["updated_at"] or "" for r in _region_rows(store, run_id)}
    params = {"include_filtered": cfg.api.include_filtered, "min_cabin_pct": cfg.api.min_cabin_pct}
    todo = candidates[: cfg.enrich.max_calls]
    stats.left_over = len(candidates) - len(todo)
    for i, avail_id in enumerate(todo):
        try:
            body, _ = client.get(f"trips/{avail_id}", params)
        except NotFound:
            stats.called += 1
            stats.expired += 1
            store.mark_expired(avail_id, updated[avail_id])
            continue
        except CapReached as e:
            log.warning("%s", e)
            stats.cap_reached = True
            stats.left_over += len(todo) - i
            break
        stats.called += 1
        raw = body.get("data") if isinstance(body, dict) else body
        trips = [parse_trip(t) for t in raw or []]
        store.save_trips(avail_id, updated[avail_id], trips, _primary_link(body), body)
        stats.priced += 1
    return stats


def shortlist_candidates(store: Store, cfg: Config, run_id: int) -> list[str]:
    """Availabilities on the run's Shortlist whose trip details are not stored yet, best first.
    Their fees are already known from the summary; the trips add flight numbers, times and the
    booking link, so only results worth acting on cost a Get Trips call."""
    from mmscan.offers import load_current
    from mmscan.report import shortlist

    in_run = {r["id"] for r in _region_rows(store, run_id)}  # only this run's calls can fetch them
    out: list[str] = []
    for s in shortlist(load_current(store), cfg):
        if s.availability_id not in in_run or s.availability_id in out:
            continue
        if store.has_fetch(s.availability_id, s.updated_at or ""):
            continue
        out.append(s.availability_id)
    return out


def fee_spread(
    store: Store, usd_to_eur: float | None = None, rates: dict[str, float] | None = None
) -> list[tuple[str, str, str, int, float, float, float]]:
    """Min, median and max fee per route and cabin over every stored trip (builder call 10)."""
    rows = store.conn.execute(
        "SELECT DISTINCT t.id, t.updated_at, a.origin, a.destination, t.cabin, t.total_taxes, "
        "t.taxes_currency FROM trips t JOIN availabilities a "
        "ON a.id = t.availability_id AND a.updated_at = t.updated_at"
    ).fetchall()
    groups: dict[tuple, list[float]] = {}
    for r in rows:
        fee = fees_eur(r["total_taxes"] or 0, r["taxes_currency"] or "", usd_to_eur, rates)
        if fee is not None:
            groups.setdefault((r["origin"], r["destination"], r["cabin"]), []).append(fee)
    return [
        (o, d, c, len(v), min(v), statistics.median(v), max(v))
        for (o, d, c), v in sorted(groups.items())
    ]

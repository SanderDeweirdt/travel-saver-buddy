"""Steps 1 and 2: scan region pairs (Bulk Availability) and the watchlist (Cached Search)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date
from typing import Any

from mmscan.client import ApiError, CapReached, Client
from mmscan.config import Config
from mmscan.models import parse_trip
from mmscan.store import Store

log = logging.getLogger("mmscan.scan")


def paginate(
    client: Client,
    path: str,
    params: dict[str, Any],
    take: int,
    on_page: Callable[[list[dict]], None] | None = None,
) -> tuple[list[dict], list[str]]:
    """Fetch every page, deduplicated by ID. `on_page` gets each page's new items as they arrive,
    so a cap hit mid-scan keeps what was already fetched."""
    items: list[dict] = []
    seen: set[str] = set()
    warnings: list[str] = []
    retrieved = 0
    cursor = None
    while True:
        page_params = {**params, "take": take}
        if retrieved:
            page_params["skip"] = retrieved
            page_params["cursor"] = cursor
        body, _ = client.get(path, page_params)
        page = body.get("data") if isinstance(body, dict) else body
        page = page or []
        if cursor is None and isinstance(body, dict):
            cursor = body.get("cursor")
        retrieved += len(page)
        new = [it for it in page if str(it.get("ID")) not in seen]
        seen.update(str(it.get("ID")) for it in new)
        items.extend(new)
        if on_page and new:
            on_page(new)
        has_more = isinstance(body, dict) and bool(body.get("hasMore"))
        if not has_more:
            break
        if not new:
            msg = f"/{path}: page at skip={page_params.get('skip', 0)} added no new ID; stopped"
            log.warning(msg)
            warnings.append(msg)
            break
    return items, warnings


def _common(cfg: Config, today: date) -> dict[str, Any]:
    start, end = cfg.date_range(today)
    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "include_filtered": cfg.api.include_filtered,
        "min_cabin_pct": cfg.api.min_cabin_pct,
    }


def region_requests(cfg: Config, today: date) -> list[tuple[str, dict]]:
    cabin = cfg.cabins[0] if len(cfg.cabins) == 1 else None
    out = []
    for pair in cfg.region_pairs:
        params = {
            "source": cfg.source,
            "cabin": cabin,
            "origin_region": pair.origin,
            "destination_region": pair.destination,
            **_common(cfg, today),
        }
        out.append(("availability", {k: v for k, v in params.items() if v is not None}))
    return out


def watchlist_requests(cfg: Config, today: date) -> list[tuple[str, dict]]:
    wl = cfg.watchlist
    if not wl.origins or not wl.destinations:
        return []
    directions = [(wl.origins, wl.destinations)]
    if wl.both_directions:
        directions.append((wl.destinations, wl.origins))
    cabins = cfg.cabins[0] if len(cfg.cabins) == 1 else None
    out = []
    for origins, dests in directions:
        params = {
            "origin_airport": ",".join(origins),
            "destination_airport": ",".join(dests),
            "sources": cfg.source,
            "cabins": cabins,
            "order_by": "lowest_mileage",
            "include_trips": True,
            **_common(cfg, today),
        }
        out.append(("search", {k: v for k, v in params.items() if v is not None}))
    return out


def planned_requests(cfg: Config, today: date) -> list[tuple[str, dict]]:
    """First-page requests of a scan; page counts are only known once it runs."""
    take = {"take": cfg.api.take}
    return [(p, {**params, **take}) for p, params in region_requests(cfg, today)] + [
        (p, {**params, **take}) for p, params in watchlist_requests(cfg, today)
    ]


def scan_regions(client: Client, store: Store, cfg: Config, run_id: int, today: date) -> dict:
    stats = {"region_results": 0, "warnings": []}
    for path, params in region_requests(cfg, today):

        def save(page: list[dict]) -> None:
            for avail in page:
                store.save_availability(run_id, avail, "region")

        items, warns = paginate(client, path, params, cfg.api.take, on_page=save)
        stats["region_results"] += len(items)
        stats["warnings"].extend(warns)
    return stats


def scan_watchlist(client: Client, store: Store, cfg: Config, run_id: int, today: date) -> dict:
    stats = {"watchlist_results": 0, "trips": 0, "warnings": []}
    for path, params in watchlist_requests(cfg, today):

        def save(page: list[dict]) -> None:
            for avail in page:
                store.save_availability(run_id, avail, "watchlist")
                raw_trips = avail.get("AvailabilityTrips")
                if raw_trips is None:
                    continue
                trips = [parse_trip(t) for t in raw_trips]
                store.save_trips(
                    str(avail["ID"]), avail.get("UpdatedAt") or "", trips, None, raw_trips
                )
                stats["trips"] += len(trips)

        items, warns = paginate(client, path, params, cfg.api.take, on_page=save)
        stats["watchlist_results"] += len(items)
        stats["warnings"].extend(warns)
    return stats


def run_scan(
    client: Client, store: Store, cfg: Config, run_id: int, today: date
) -> tuple[str, dict]:
    """Scan regions, then the watchlist, and close the run. Returns (status, stats).

    A cap hit or API error stops the scan; everything stored so far is kept and counted."""
    status = "ok"
    warnings: list[str] = []
    try:
        warnings += scan_regions(client, store, cfg, run_id, today)["warnings"]
        warnings += scan_watchlist(client, store, cfg, run_id, today)["warnings"]
    except CapReached as e:
        status = "partial"
        warnings.append(str(e))
    except ApiError as e:
        status = "failed"
        warnings.append(str(e))
    stats = store.scan_counts(run_id)
    stats["calls"] = client.calls_made
    store.finish_run(run_id, status, stats, warnings)
    stats["warnings"] = warnings
    return status, stats

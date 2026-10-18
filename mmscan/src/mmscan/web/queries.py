"""Read-only queries for the dashboard. Nothing here writes or calls the API."""

from __future__ import annotations

import json
import statistics
from datetime import datetime, timedelta

from mmscan.baseline import baseline_for, build_baselines, thin_routes
from mmscan.config import Config
from mmscan.deals import rank_deals, saving_verdict
from mmscan.offers import load_current, route_points
from mmscan.overview import directions, in_regions
from mmscan.report import _age_hours, shortlist
from mmscan.scoring import rank_key
from mmscan.store import Store

SORTS = {
    "verdict": rank_key,
    "total": lambda s: (s.total_eur is None, s.total_eur),
    "miles": lambda s: (s.miles is None, s.miles),
    "date": lambda s: (s.date is None, s.date),
    "saving": lambda s: (s.saving_eur is None, -(s.saving_eur or 0)),
}


def recent_runs(store: Store, limit: int = 100) -> list[dict]:
    rows = store.conn.execute(
        "SELECT r.id, r.kind, r.started_at, r.finished_at, r.status, r.stats_json, "
        "r.warnings_json, (SELECT count(*) FROM api_calls c WHERE c.run_id = r.id) AS calls "
        "FROM runs r ORDER BY r.id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [
        {
            "id": r["id"],
            "kind": r["kind"],
            "started_at": r["started_at"],
            "finished_at": r["finished_at"],
            "status": r["status"],
            "calls": r["calls"],
            "stats": json.loads(r["stats_json"] or "{}"),
            "warnings": json.loads(r["warnings_json"] or "[]"),
        }
        for r in rows
    ]


def last_update(store: Store) -> str | None:
    """When a price on the pages was last confirmed by a scan; None before the first one."""
    row = store.conn.execute("SELECT max(last_seen) FROM current_offers").fetchone()
    return row[0]


def shortlist_view(
    store: Store,
    cfg: Config,
    now: datetime,
    route: str = "",
    cabin: str = "",
    verdict: str = "",
    sort: str = "verdict",
    show_all: bool = False,
) -> dict:
    results = load_current(store)
    rows = results if show_all else shortlist(results, cfg)
    routes = sorted({f"{s.origin}-{s.destination}" for s in rows})
    if route:
        rows = [s for s in rows if f"{s.origin}-{s.destination}" == route]
    if cabin:
        rows = [s for s in rows if s.cabin == cabin]
    if verdict:
        rows = [s for s in rows if s.verdict == verdict]
    rows = sorted(rows, key=SORTS.get(sort, rank_key))
    baselines = build_baselines(results, cfg)
    out = []
    for s in rows:
        b = baseline_for(baselines, cfg, s)
        out.append(
            {
                "s": s,
                "baseline": b.median if b else None,
                "samples": b.n if b else 0,
                "age_h": _age_hours(s.updated_at, now),
                "pricing": cfg.pricing_model(s.carriers),
                "why": cfg.focus_reasons(
                    s.origin, s.origin_region, s.destination, s.destination_region, s.cabin
                ),
            }
        )
    return {
        "rows": out,
        "routes": routes,
        "cabins": sorted({s.cabin for s in results}),
        "verdicts": sorted({s.verdict for s in results}),
        "total": len(results),
    }


def deals_view(store: Store, cfg: Config, now: datetime, direction: str = "", **filters) -> dict:
    """Every route on offer, one row per flight at its latest price; `filters` go to rank_deals."""
    everything = load_current(store)
    results = in_regions(everything, cfg, direction)
    baselines = build_baselines(everything, cfg)
    out = rank_deals(results, baselines, cfg, now, **filters)
    out["total"] = len(results)
    out["thin_routes"] = thin_routes(baselines)
    out["directions"] = directions(cfg)
    return out


def route_history(
    store: Store, cfg: Config, origin: str, destination: str, cabin: str, now: datetime
) -> dict:
    points = route_points(store, cfg, origin, destination, cabin, now)
    current = [
        s
        for s in load_current(store)
        if (s.origin, s.destination, s.cabin) == (origin, destination, cabin)
    ]
    baselines = build_baselines(current, cfg)
    here = list(baselines.values())  # one per pricing group
    usual = max((b for b in here if b.ready), key=lambda b: b.n, default=None)
    rows = []
    for s in sorted(current, key=rank_key):
        b = baseline_for(baselines, cfg, s)
        save = b.median - s.total_eur if b and s.total_eur is not None else None
        rows.append(
            {
                "s": s,
                "usual": b.median if b else None,
                "save": save,
                "pct": save / b.median * 100 if save is not None else None,
                "verdict": saving_verdict(save / b.median * 100, cfg) if save is not None else None,
                "pricing": cfg.pricing_model(s.carriers),
            }
        )
    priced = [r for r in rows if r["save"] is not None and r["s"].expired is False]
    best = max(priced, key=lambda r: r["pct"], default=None)
    return {
        "points": points,
        "rows": rows,
        "usual": usual,
        "samples_seen": max((b.n for b in here), default=0),
        "min_samples": cfg.relative.min_samples,
        "best": best,
    }


def carrier_trust(checks: list[dict], cfg: Config) -> list[dict]:
    """Live-to-cached mile ratio per carrier from the manual checks. Dynamic carriers are always
    listed, even before a first check; fixed-chart carriers only once they have one."""
    by: dict[str, list[float]] = {}
    for c in checks:
        if c["cached_miles"]:
            by.setdefault(c["carrier"], []).append(c["live_miles"] / c["cached_miles"])
    dynamic = {c.upper() for c in cfg.dynamic_airlines}
    out = []
    for carrier in sorted(dynamic | set(by)):
        r = by.get(carrier, [])
        out.append(
            {
                "carrier": carrier,
                "basis": "dynamic" if carrier in dynamic else "fixed",
                "n": len(r),
                "median": statistics.median(r) if r else None,
                "lo": min(r) if r else None,
                "hi": max(r) if r else None,
            }
        )
    return out


def routes_view(store: Store, cfg: Config) -> dict:
    """How much the pages cover: airport-to-airport routes with a current price, how many of them
    are watchlist pairs, and the flights (route, date, cabin) on offer."""
    pairs = store.conn.execute(
        "SELECT DISTINCT origin, destination FROM current_offers WHERE origin IS NOT NULL"
    ).fetchall()
    wl = cfg.watchlist
    on_watchlist = sum(
        1
        for o, d in (tuple(p) for p in pairs)
        if (o in wl.origins and d in wl.destinations)
        or (wl.both_directions and o in wl.destinations and d in wl.origins)
    )
    flights = store.conn.execute("SELECT count(*) FROM current_offers").fetchone()[0]
    return {
        "routes": len(pairs),
        "on_watchlist": on_watchlist,
        "watchlist_pairs": len(wl.origins)
        * len(wl.destinations)
        * (2 if wl.both_directions else 1),
        "flights": flights,
    }


def data_view(store: Store, cfg: Config, now: datetime) -> dict:
    runs = recent_runs(store, 30)
    week = (now - timedelta(days=7)).isoformat()
    last_watch = next((r for r in runs if r["kind"] == "watch"), None)
    last_full = next((r for r in runs if r["kind"] == "run"), None)
    age = cfg.usd_rate_age_days(now.date())
    watch_age_h = (
        (now - datetime.fromisoformat(last_watch["started_at"])).total_seconds() / 3600
        if last_watch
        else None
    )
    return {
        "quota": quota_view(store, cfg.api.daily_call_cap, now),
        "coverage": routes_view(store, cfg),
        "runs": runs[:10],
        "last_watch": last_watch,
        "last_full": last_full,
        "watch_age_h": watch_age_h,
        "failed_week": sum(
            1 for r in runs if r["status"] in ("failed", "partial") and r["started_at"] >= week
        ),
        "fx": {"rate": cfg.usd_to_eur, "age_days": age, "stale": age is None or age > 30},
        "trust": carrier_trust(store.price_checks(), cfg),
    }


def quota_view(store: Store, cap: int, now: datetime) -> dict:
    days = store.conn.execute(
        "SELECT substr(ts, 1, 10) AS day, count(*) AS n FROM api_calls "
        "GROUP BY substr(ts, 1, 10) ORDER BY day DESC LIMIT 7"
    ).fetchall()
    used = store.calls_today(now)
    return {
        "used": used,
        "cap": cap,
        "pct": min(100, round(used / cap * 100)) if cap else 0,
        "remaining_header": store.last_rate_remaining(),
        "days": [(d["day"], d["n"]) for d in days],
    }

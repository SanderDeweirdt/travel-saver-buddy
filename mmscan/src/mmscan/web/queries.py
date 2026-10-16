"""Read-only queries for the dashboard. Nothing here writes or calls the API."""

from __future__ import annotations

import json
import statistics
from datetime import datetime, timedelta

from mmscan.baseline import baseline_for, route_baselines, thin_routes
from mmscan.config import Config
from mmscan.deals import rank_deals, saving_verdict
from mmscan.overview import route_overview
from mmscan.report import _age_hours, eligible, load_results, shortlist
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


def scored_runs(store: Store, limit: int = 30) -> list[dict]:
    rows = store.conn.execute(
        "SELECT r.id, r.kind, r.started_at FROM runs r WHERE r.id IN "
        "(SELECT DISTINCT run_id FROM results) ORDER BY r.id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(zip(("id", "kind", "started_at"), tuple(r), strict=True)) for r in rows]


def shortlist_view(
    store: Store,
    cfg: Config,
    run_id: int,
    now: datetime,
    route: str = "",
    cabin: str = "",
    verdict: str = "",
    sort: str = "verdict",
    show_all: bool = False,
) -> dict:
    results = load_results(store, run_id)
    rows = results if show_all else shortlist(results, cfg)
    routes = sorted({f"{s.origin}-{s.destination}" for s in rows})
    if route:
        rows = [s for s in rows if f"{s.origin}-{s.destination}" == route]
    if cabin:
        rows = [s for s in rows if s.cabin == cabin]
    if verdict:
        rows = [s for s in rows if s.verdict == verdict]
    rows = sorted(rows, key=SORTS.get(sort, rank_key))
    baselines = route_baselines(store, cfg, run_id, now)
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
            }
        )
    return {
        "rows": out,
        "routes": routes,
        "cabins": sorted({s.cabin for s in results}),
        "verdicts": sorted({s.verdict for s in results}),
        "total": len(results),
    }


def deals_view(store: Store, cfg: Config, run_id: int, now: datetime, **filters) -> dict:
    results = eligible(load_results(store, run_id), cfg)
    baselines = route_baselines(store, cfg, run_id, now)
    out = rank_deals(results, baselines, cfg, now, **filters)
    out["total"] = len(results)
    out["thin_routes"] = thin_routes(baselines)
    return out


def overview_view(store: Store, cfg: Config, run_id: int, now: datetime, **filters) -> dict:
    """Every Europe/Asia route in the run, not only the focus set."""
    results = load_results(store, run_id)
    baselines = route_baselines(store, cfg, run_id, now)
    return {
        "rows": route_overview(results, baselines, cfg, now, **filters),
        "directions": [f"{p.origin} → {p.destination}" for p in cfg.region_pairs],
    }


def route_history(
    store: Store, cfg: Config, origin: str, destination: str, cabin: str, now: datetime
) -> dict:
    cutoff = (now - timedelta(days=180)).isoformat()
    rows = store.conn.execute(
        "SELECT r.run_id, u.started_at, r.total_eur FROM results r JOIN runs u ON u.id = r.run_id "
        "WHERE r.origin=? AND r.destination=? AND r.cabin=? AND r.total_eur IS NOT NULL "
        "AND r.expired = 0 AND u.started_at >= ? ORDER BY r.run_id",
        (origin, destination, cabin, cutoff),
    ).fetchall()
    by_run: dict[int, list] = {}
    for r in rows:
        by_run.setdefault(r["run_id"], [r["started_at"], []])[1].append(r["total_eur"])
    points = [
        {
            "run_id": run_id,
            "ts": ts,
            "low": min(v),
            "median": statistics.median(v),
            "n": len(v),
        }
        for run_id, (ts, v) in by_run.items()
    ]
    latest = max(by_run) if by_run else None
    current = (
        [
            s
            for s in load_results(store, latest)
            if (s.origin, s.destination, s.cabin) == (origin, destination, cabin)
        ]
        if latest
        else []
    )
    baselines = route_baselines(store, cfg, latest, now) if latest else {}
    here = [
        b for k, b in baselines.items() if k[:3] == (origin, destination, cabin)
    ]  # one per pricing group
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
        "latest_run": latest,
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

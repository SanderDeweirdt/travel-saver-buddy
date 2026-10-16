"""The usual price of a route: median total cost of what has been seen over `history_days`.

Fixed-chart and dynamic carriers get separate baselines, so a chart fare is never judged against
dynamic fares (or the reverse). Fewer than `relative.min_samples` observations is not a baseline.
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

from mmscan.config import Config
from mmscan.report import load_results
from mmscan.scoring import Scored
from mmscan.store import Store

Key = tuple[str | None, str | None, str, str]  # origin, destination, cabin, "fixed" | "dynamic"


@dataclass(frozen=True)
class Baseline:
    median: float
    n: int
    ready: bool  # n has reached relative.min_samples


def price_group(cfg: Config, carriers: str | None) -> str:
    """ "fixed" for chart carriers; dynamic and mixed routings are judged as dynamic."""
    return "fixed" if cfg.pricing_model(carriers) == "fixed" else "dynamic"


def baseline_key(cfg: Config, s: Scored) -> Key:
    return (s.origin, s.destination, s.cabin, price_group(cfg, s.carriers))


def build_baselines(samples: list[Scored], cfg: Config) -> dict[Key, Baseline]:
    """Samples are in the order seen; the latest observation of each flight and cabin wins."""
    latest = {s.key: s for s in samples if not s.expired and s.total_eur is not None}
    totals: dict[Key, list[float]] = {}
    for s in latest.values():
        totals.setdefault(baseline_key(cfg, s), []).append(s.total_eur)
    n_min = cfg.relative.min_samples
    return {k: Baseline(statistics.median(v), len(v), len(v) >= n_min) for k, v in totals.items()}


CACHE_SECONDS = 600
_cache: dict[tuple, tuple[float, dict[Key, Baseline]]] = {}


def _history_latest(
    store: Store, cfg: Config, run_id: int, now: datetime
) -> dict[tuple, tuple[Key, float]]:
    """Latest observation of each flight over `history_days`, other runs only. Reads just the six
    columns it needs: this runs over every stored result of the last month."""
    cutoff = (now - timedelta(days=cfg.relative.history_days)).isoformat()
    rows = store.conn.execute(
        "SELECT r.origin, r.destination, r.date, r.cabin, r.carriers, r.total_eur "
        "FROM results r JOIN runs u ON u.id = r.run_id "
        "WHERE r.run_id != ? AND u.started_at >= ? AND r.total_eur IS NOT NULL AND r.expired = 0 "
        "ORDER BY r.run_id",
        (run_id, cutoff),
    )
    out: dict[tuple, tuple[Key, float]] = {}
    for o, d, date, cabin, carriers, total in (tuple(r) for r in rows):
        out[(o, d, date, cabin)] = ((o, d, cabin, price_group(cfg, carriers)), total)
    return out


def route_baselines(store: Store, cfg: Config, run_id: int, now: datetime) -> dict[Key, Baseline]:
    """Baselines from the stored history plus the given run (which wins on repeats).

    Cached for ten minutes per database and run: the history is immutable, and every page view
    would otherwise re-read a month of results."""
    current = load_results(store, run_id)
    stamp = (store.ident, run_id, len(current), cfg.relative.history_days, cfg.relative.min_samples)
    hit = _cache.get(stamp)
    if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
        return hit[1]
    latest = _history_latest(store, cfg, run_id, now)
    for s in current:
        if not s.expired and s.total_eur is not None:
            latest[s.key] = (baseline_key(cfg, s), s.total_eur)
    totals: dict[Key, list[float]] = {}
    for key, total in latest.values():
        totals.setdefault(key, []).append(total)
    n_min = cfg.relative.min_samples
    out = {k: Baseline(statistics.median(v), len(v), len(v) >= n_min) for k, v in totals.items()}
    _cache[stamp] = (time.monotonic(), out)
    return out


def baseline_for(baselines: dict[Key, Baseline], cfg: Config, s: Scored) -> Baseline | None:
    """The route's baseline when it has enough samples, else None."""
    b = baselines.get(baseline_key(cfg, s))
    return b if b and b.ready else None


def thin_routes(baselines: dict[Key, Baseline]) -> int:
    return sum(1 for b in baselines.values() if not b.ready)

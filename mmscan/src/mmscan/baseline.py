"""The usual price of a route: median total cost of what has been seen over `history_days`.

Fixed-chart and dynamic carriers get separate baselines, so a chart fare is never judged against
dynamic fares (or the reverse). Fewer than `relative.min_samples` observations is not a baseline.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime

from mmscan.config import Config
from mmscan.report import load_results
from mmscan.scoring import Scored, history_rows
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


def route_baselines(store: Store, cfg: Config, run_id: int, now: datetime) -> dict[Key, Baseline]:
    """Baselines from the stored history plus the given run (which wins on repeats)."""
    return build_baselines(history_rows(store, cfg, run_id, now) + load_results(store, run_id), cfg)


def baseline_for(baselines: dict[Key, Baseline], cfg: Config, s: Scored) -> Baseline | None:
    """The route's baseline when it has enough samples, else None."""
    b = baselines.get(baseline_key(cfg, s))
    return b if b and b.ready else None


def thin_routes(baselines: dict[Key, Baseline]) -> int:
    return sum(1 for b in baselines.values() if not b.ready)

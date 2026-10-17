"""The usual price of a route: the median total cost over the dates currently on offer.

Fixed-chart and dynamic carriers get separate baselines, so a chart fare is never judged against
dynamic fares (or the reverse). Fewer than `relative.min_samples` offers is not a baseline.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from mmscan.config import Config
from mmscan.offers import load_current
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
    """One sample per flight and cabin (the latest, if given several)."""
    latest = {s.key: s for s in samples if not s.expired and s.total_eur is not None}
    totals: dict[Key, list[float]] = {}
    for s in latest.values():
        totals.setdefault(baseline_key(cfg, s), []).append(s.total_eur)
    n_min = cfg.relative.min_samples
    return {k: Baseline(statistics.median(v), len(v), len(v) >= n_min) for k, v in totals.items()}


def route_baselines(store: Store, cfg: Config) -> dict[Key, Baseline]:
    """Baselines from the current offers: the usual price of a route is the median over the dates
    currently on offer. Pages that already hold the offers call `build_baselines` on them."""
    return build_baselines(load_current(store), cfg)


def baseline_for(baselines: dict[Key, Baseline], cfg: Config, s: Scored) -> Baseline | None:
    """The route's baseline when it has enough samples, else None."""
    b = baselines.get(baseline_key(cfg, s))
    return b if b and b.ready else None


def thin_routes(baselines: dict[Key, Baseline]) -> int:
    return sum(1 for b in baselines.values() if not b.ready)

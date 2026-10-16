"""One row per route and cabin across every configured region pair. Pure functions: no I/O."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from mmscan.baseline import Baseline, Key, baseline_for
from mmscan.config import Config
from mmscan.deals import STALE_HOURS, saving_verdict
from mmscan.report import _age_hours
from mmscan.scoring import Scored

SORTS = ("route", "total", "pct", "date", "count")


@dataclass(frozen=True)
class RouteRow:
    direction: str  # "Europe → Asia"
    origin: str
    destination: str
    cabin: str
    cheapest: Scored  # lowest total seen for the route and cabin
    pricing: str  # "fixed", "dynamic" or "mixed" for the cheapest one
    dates: int  # distinct departure dates with a price
    usual: float | None  # route baseline, None while history is thin
    save_pct: float | None
    verdict: str | None
    age_h: float | None

    @property
    def verified(self) -> bool:
        return self.pricing == "fixed"


def _direction(cfg: Config, s: Scored) -> str | None:
    for p in cfg.region_pairs:
        if (s.origin_region, s.destination_region) == (p.origin, p.destination):
            return f"{p.origin} → {p.destination}"
    return None


def route_overview(
    results: list[Scored],
    baselines: dict[Key, Baseline],
    cfg: Config,
    now: datetime,
    *,
    cabin: str = "",
    direction: str = "",
    route: str = "",
    hide_stale: bool = True,
    sort: str = "route",
) -> list[RouteRow]:
    """Cheapest result per origin, destination and cabin over all region pairs."""
    q = "".join(ch for ch in route.upper() if ch.isalnum())
    groups: dict[tuple, list[Scored]] = {}
    for s in results:
        if s.expired or s.fee_estimated or s.total_eur is None or not s.origin or not s.destination:
            continue
        if cabin and s.cabin != cabin:
            continue
        d = _direction(cfg, s)
        if d is None or (direction and d != direction):
            continue
        if q and q not in f"{s.origin}{s.destination}":
            continue
        age = _age_hours(s.updated_at, now)
        if hide_stale and age is not None and age > STALE_HOURS:
            continue
        groups.setdefault((d, s.origin, s.destination, s.cabin), []).append(s)

    rows: list[RouteRow] = []
    for (d, o, dst, c), items in groups.items():
        best = min(items, key=lambda s: (s.total_eur, s.date or ""))
        b = baseline_for(baselines, cfg, best)
        pct = (b.median - best.total_eur) / b.median * 100 if b else None
        rows.append(
            RouteRow(
                d, o, dst, c, best, cfg.pricing_model(best.carriers),
                len({s.date for s in items}), b.median if b else None, pct,
                saving_verdict(pct, cfg) if pct is not None else None,
                _age_hours(best.updated_at, now),
            )
        )  # fmt: skip
    keys = {
        "route": lambda r: (r.direction, r.origin, r.destination, r.cabin),
        "total": lambda r: r.cheapest.total_eur,
        "pct": lambda r: (r.save_pct is None, -(r.save_pct or 0)),
        "date": lambda r: r.cheapest.date or "",
        "count": lambda r: -r.dates,
    }
    rows.sort(key=keys.get(sort, keys["route"]))
    return rows

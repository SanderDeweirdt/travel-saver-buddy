"""Deals ranked by how far below the route's usual price they are. Pure functions: no I/O."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from mmscan.baseline import Baseline, Key, baseline_for, baseline_key
from mmscan.config import Config
from mmscan.report import _age_hours
from mmscan.scoring import Scored

GREAT, GOOD, MARGINAL, ABOVE = "Great deal", "Good deal", "Marginal", "Above usual"
STALE_HOURS = 48
SORTS = ("pct", "save", "total", "date")


def saving_verdict(pct: float, cfg: Config) -> str:
    if pct >= cfg.savings.great_pct:
        return GREAT
    if pct >= cfg.savings.good_pct:
        return GOOD
    return MARGINAL if pct >= 0 else ABOVE


@dataclass(frozen=True)
class Deal:
    s: Scored
    pax: int
    pricing: str  # "fixed", "dynamic" or "mixed" (see Config.pricing_model)
    age_h: float | None
    usual: float | None  # per person; None while the route has too little history
    save: float | None  # per person; negative when above the usual price
    save_pct: float | None
    verdict: str | None

    @property
    def verified(self) -> bool:
        """A fixed-chart price: the cached miles can be trusted. Dynamic prices are not."""
        return self.pricing == "fixed"

    @property
    def party_miles(self) -> int:
        return (self.s.miles or 0) * self.pax

    @property
    def party_fees(self) -> float:
        return (self.s.fees_eur or 0) * self.pax

    @property
    def party_total(self) -> float:
        return (self.s.total_eur or 0) * self.pax

    @property
    def party_usual(self) -> float | None:
        return None if self.usual is None else self.usual * self.pax

    @property
    def party_save(self) -> float | None:
        return None if self.save is None else self.save * self.pax

    @property
    def save_ct_per_mile(self) -> float | None:
        if self.save is None or not self.s.miles:
            return None
        return self.save / self.s.miles * 100


def _matches_route(s: Scored, text: str) -> bool:
    q = "".join(ch for ch in text.upper() if ch.isalnum())
    return q in f"{s.origin}{s.destination}"


def rank_deals(
    results: list[Scored],
    baselines: dict[Key, Baseline],
    cfg: Config,
    now: datetime,
    *,
    cabin: str = "",
    route: str = "",
    chart_only: bool = False,
    hide_chart: bool = False,
    min_pct: float | None = None,
    inline_building: bool = False,
    hide_stale: bool = True,
    pax: int = 1,
    sort: str = "pct",
) -> dict:
    """Split priced results into `deals` (have a usual price) and `building` (too little
    history), after the filters. Seats below `pax` hide a result; unknown seats (None or 0) stay.
    `min_pct` keeps only deals at least that far below the usual price. `inline_building` puts
    results without a usual price in `deals` too, with no saving, instead of in `building`."""
    deals: list[Deal] = []
    building: list[tuple[Scored, int]] = []
    for s in results:
        if s.expired or s.fee_estimated or s.total_eur is None:
            continue
        if cabin and s.cabin != cabin:
            continue
        if route and not _matches_route(s, route):
            continue
        pricing = cfg.pricing_model(s.carriers)
        if chart_only and not hide_chart and pricing != "fixed":
            continue
        if hide_chart and pricing == "fixed":
            continue
        age = _age_hours(s.updated_at, now)
        if hide_stale and age is not None and age > STALE_HOURS:
            continue
        if s.seats and s.seats < pax:
            continue
        b = baseline_for(baselines, cfg, s)
        if b is None:
            if inline_building and min_pct is None:
                deals.append(Deal(s, pax, pricing, age, None, None, None, None))
                continue
            known = baselines.get(baseline_key(cfg, s))
            building.append((s, known.n if known else 0))
            continue
        save = b.median - s.total_eur
        pct = save / b.median * 100
        if min_pct is not None and pct < min_pct:
            continue
        deals.append(Deal(s, pax, pricing, age, b.median, save, pct, saving_verdict(pct, cfg)))

    keys = {
        "pct": lambda d: (d.save is None, -(d.save_pct or 0)),
        "save": lambda d: (d.save is None, -(d.save or 0)),
        "total": lambda d: d.s.total_eur,
        "date": lambda d: d.s.date or "",
    }
    deals.sort(key=keys.get(sort, keys["pct"]))
    building.sort(key=lambda t: t[0].total_eur)
    best = max(
        (d for d in deals if d.verified and d.save is not None and d.save > 0),
        key=lambda d: d.save_pct,
        default=None,
    )
    return {
        "deals": deals,
        "building": building,
        "best": best,
        "good_count": sum(
            1 for d in deals if d.save_pct is not None and d.save_pct >= cfg.savings.good_pct
        ),
        "new_count": sum(1 for d in deals if d.s.change == "New"),
        "pax": pax,
    }

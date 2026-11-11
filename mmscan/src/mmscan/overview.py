"""Which results count as "all routes": every region pair in the config. Pure functions."""

from __future__ import annotations

from mmscan.config import REGIONS, Config
from mmscan.scoring import Scored


def directions(cfg: Config) -> list[str]:
    return [f"{p.origin} → {p.destination}" for p in cfg.region_pairs]


def in_regions(results: list[Scored], cfg: Config, direction: str = "") -> list[Scored]:
    """Results whose regions match a configured region pair (and `direction`, when given).
    Not limited to the shortlist focus."""
    pairs = {
        (p.origin, p.destination)
        for p in cfg.region_pairs
        if not direction or f"{p.origin} → {p.destination}" == direction
    }
    return [s for s in results if (s.origin_region, s.destination_region) in pairs]


def place_options(results: list[Scored], cfg: Config) -> list[dict]:
    """What the Origin and Destination pickers offer: the regions on offer, the configured
    subregions, then every airport seen in `results` (with its region)."""
    regions = sorted({r for p in cfg.region_pairs for r in (p.origin, p.destination)})
    out = [{"value": r, "label": r, "kind": "Region", "hint": ""} for r in regions]
    out += [
        {"value": k, "label": k.replace("_", " ").title(), "kind": "Region", "hint": ""}
        for k in sorted(cfg.subregions)
    ]
    airports: dict[str, str] = {}
    for s in results:
        if s.origin:
            airports.setdefault(s.origin, s.origin_region or "")
        if s.destination:
            airports.setdefault(s.destination, s.destination_region or "")
    out += [
        {"value": code, "label": code, "kind": "Airport", "hint": region}
        for code, region in sorted(airports.items())
    ]
    return out


def matches_place(spec: str, airport: str | None, region: str | None, cfg: Config) -> bool:
    """Does an airport (and its region) fall under `spec`: an airport code, a region or a
    subregion key? An empty spec matches everything."""
    spec = (spec or "").strip()
    if not spec:
        return True
    if spec in cfg.subregions:
        return airport in cfg.subregions[spec]
    if spec.casefold() in {r.casefold() for r in REGIONS}:
        return (region or "").casefold() == spec.casefold()
    return (airport or "").upper() == spec.upper()

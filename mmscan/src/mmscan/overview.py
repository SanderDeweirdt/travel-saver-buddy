"""Which results count as "all routes": every region pair in the config. Pure functions."""

from __future__ import annotations

from mmscan.config import Config
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

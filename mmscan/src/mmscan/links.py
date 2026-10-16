"""Link to Miles & More for one flight, so a price can be checked by hand."""

from __future__ import annotations

from urllib.parse import quote

from mmscan.config import Config
from mmscan.scoring import Scored


def mm_link(cfg: Config, s: Scored, pax: int = 1) -> str | None:
    """The link seats.aero stored for this flight, else the configured template filled in.
    None when neither exists (no template set, or the flight lacks a route or date)."""
    if s.booking_link:
        return s.booking_link
    template = cfg.miles_and_more.link_template
    if not template or not (s.origin and s.destination and s.date):
        return None
    values = {
        "origin": s.origin,
        "destination": s.destination,
        "date": s.date,
        "cabin": s.cabin,
        "adults": str(max(1, pax)),
    }
    return template.format(**{k: quote(v, safe="") for k, v in values.items()})

"""Link to the flight's mileage program for one flight, so a price can be checked by hand."""

from __future__ import annotations

from urllib.parse import quote

from mmscan.config import Config
from mmscan.scoring import Scored

# Miles & More `bookingclass`. Only B (business) is confirmed from a real link; E and F follow the
# program's usual codes. Any other cabin gets no generated link.
CABIN_CODES = {"economy": "E", "business": "B", "first": "F"}


def mm_link(cfg: Config, s: Scored, pax: int = 1) -> str | None:
    """The link seats.aero stored for this flight, else the configured template filled in.
    None when neither exists (no template set, or the flight lacks a route or date)."""
    if s.booking_link:
        return s.booking_link
    template = cfg.link_template_for(s.source)
    if not template or not (s.origin and s.destination and s.date):
        return None
    code = CABIN_CODES.get(s.cabin)
    try:
        yyyy, mm, dd = s.date.split("-")
    except ValueError:
        return None
    if code is None:
        return None
    values = {
        "origin": s.origin,
        "destination": s.destination,
        "date": s.date,
        "date_us": f"{mm}/{dd}/{yyyy}",
        "cabin": s.cabin,
        "cabin_code": code,
        "adults": str(max(1, pax)),
    }
    return template.format(**{k: quote(v, safe="") for k, v in values.items()})

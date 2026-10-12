"""Parse seats.aero availability and trip objects into typed values."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

CABIN_PREFIX = {"economy": "Y", "premium": "W", "business": "J", "first": "F"}


@dataclass
class CabinOffer:
    cabin: str
    miles: int
    seats: int | None
    airlines: str
    direct: bool


@dataclass
class Trip:
    id: str
    availability_id: str
    cabin: str
    miles: int
    taxes_minor: int
    currency: str
    seats: int | None
    stops: int
    carriers: str
    flight_numbers: str
    departs_at: str
    arrives_at: str
    total_duration: int | None
    raw: dict = field(repr=False)


def parse_miles(value: Any) -> int | None:
    """Mileage cost as int, or None when the cabin is not available ("0", "", null)."""
    if value is None or isinstance(value, bool):
        return None
    try:
        miles = int(str(value).strip())
    except ValueError:
        return None
    return miles if miles > 0 else None


def parse_seats(value: Any) -> int | None:
    """Remaining seats; 0 or null means unknown, not sold out."""
    if value is None or isinstance(value, bool):
        return None
    try:
        seats = int(value)
    except (TypeError, ValueError):
        return None
    return seats if seats > 0 else None


def parse_cabin_offers(avail: dict, cabins: list[str]) -> list[CabinOffer]:
    offers = []
    for cabin in cabins:
        p = CABIN_PREFIX[cabin]
        if avail.get(f"{p}Available") is not True:
            continue
        miles = parse_miles(avail.get(f"{p}MileageCost"))
        if miles is None:
            continue
        offers.append(
            CabinOffer(
                cabin=cabin,
                miles=miles,
                seats=parse_seats(avail.get(f"{p}RemainingSeats")),
                airlines=avail.get(f"{p}Airlines") or "",
                direct=bool(avail.get(f"{p}Direct")),
            )
        )
    return offers


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def parse_trip(d: dict) -> Trip:
    duration = d.get("TotalDuration")
    return Trip(
        id=str(d["ID"]),
        availability_id=str(d.get("AvailabilityID") or ""),
        cabin=(d.get("Cabin") or "").lower(),
        miles=_int(d.get("MileageCost")),
        taxes_minor=_int(d.get("TotalTaxes")),
        currency=d.get("TaxesCurrency") or "",
        seats=parse_seats(d.get("RemainingSeats")),
        stops=_int(d.get("Stops")),
        carriers=d.get("Carriers") or "",
        flight_numbers=d.get("FlightNumbers") or "",
        departs_at=d.get("DepartsAt") or "",
        arrives_at=d.get("ArrivesAt") or "",
        total_duration=_int(duration) if duration is not None else None,
        raw=d,
    )


def fees_eur(taxes_minor: int, currency: str, usd_to_eur: float | None = None) -> float | None:
    """Fees in euros from minor units. Empty currency is taken as EUR (builder call 3). The live
    API reports lufthansa fees in USD, converted at the configured fixed rate. Anything else, or
    USD without a rate, is unpriced."""
    if currency in ("EUR", ""):
        return taxes_minor / 100
    if currency == "USD" and usd_to_eur:
        return round(taxes_minor / 100 * usd_to_eur, 2)
    return None


def local_time(s: str) -> str:
    """Airport local time for display. The trailing Z is not UTC, so no conversion."""
    if not s:
        return ""
    return s.rstrip("Z").replace("T", " ")[:16]

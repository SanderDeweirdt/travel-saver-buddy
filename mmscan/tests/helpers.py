"""Builders for availability and trip objects shaped like the PRD's API section."""

from __future__ import annotations

from mmscan.config import Config
from mmscan.models import CABIN_PREFIX, Trip
from mmscan.scoring import Scored

REGION = {
    "MUC": "Europe",
    "FRA": "Europe",
    "ZRH": "Europe",
    "VIE": "Europe",
    "SIN": "Asia",
    "KUL": "Asia",
    "BKK": "Asia",
    "NRT": "Asia",
}


def avail(
    id: str,
    origin: str = "MUC",
    dest: str = "SIN",
    date: str = "2026-12-10",
    updated: str = "2026-10-10T08:00:00Z",
    taxes: dict[str, int] | None = None,
    currency: str = "USD",
    airlines: str = "SQ",
    **cabins: int,
) -> dict:
    """`cabins` maps cabin name to miles, e.g. business=60000. `taxes` maps cabin name to the
    summary's TotalTaxes in minor units, as the live API returns them (in USD)."""
    a = {
        "ID": id,
        "Route": {
            "OriginAirport": origin,
            "OriginRegion": REGION[origin],
            "DestinationAirport": dest,
            "DestinationRegion": REGION[dest],
        },
        "Date": date,
        "Source": "lufthansa",
        "UpdatedAt": updated,
        "TaxesCurrency": currency,
        "AvailabilityTrips": [],
    }
    for name, p in CABIN_PREFIX.items():
        miles = cabins.get(name)
        a[f"{p}TotalTaxes"] = (taxes or {}).get(name, 0)
        a[f"{p}Available"] = miles is not None
        a[f"{p}MileageCost"] = str(miles) if miles is not None else "0"
        a[f"{p}RemainingSeats"] = 4 if miles is not None else 0
        a[f"{p}Airlines"] = airlines if miles is not None else ""
        a[f"{p}Direct"] = miles is not None
    return a


def trip(
    id: str,
    avail_id: str = "a",
    cabin: str = "business",
    miles: int = 60000,
    taxes: int = 40000,
    currency: str = "EUR",
    seats: int | None = 4,
    stops: int = 0,
    carriers: str = "SQ",
) -> Trip:
    return Trip(
        id=id,
        availability_id=avail_id,
        cabin=cabin,
        miles=miles,
        taxes_minor=taxes,
        currency=currency,
        seats=seats,
        stops=stops,
        carriers=carriers,
        flight_numbers="LH778",
        departs_at="2026-12-10T22:05:00Z",
        arrives_at="2026-12-11T17:10:00Z",
        total_duration=725,
        raw={},
    )


def scored(
    total: float | None,
    origin: str = "MUC",
    dest: str = "SIN",
    date: str = "2026-12-10",
    cabin: str = "business",
    miles: int = 60000,
    fees: float | None = 50.0,
    estimated: bool = False,
    seats_ok: bool = True,
    direct: bool = True,
    id: str | None = None,
    carriers: str = "SQ",
) -> Scored:
    return Scored(
        availability_id=id or f"{origin}{dest}{date}{cabin}",
        cabin=cabin,
        date=date,
        origin=origin,
        destination=dest,
        origin_region=REGION[origin],
        destination_region=REGION[dest],
        miles=miles,
        fees_eur=fees,
        fee_estimated=estimated,
        total_eur=total,
        seats=4,
        stops=0 if direct else 1,
        carriers=carriers,
        flight_numbers="LH778",
        departs_at=None,
        arrives_at=None,
        booking_link=None,
        updated_at="2026-10-10T08:00:00Z",
        seats_ok=seats_ok,
        direct=direct,
    )


def config(default_config_dict: dict, **overrides) -> Config:
    data = {**default_config_dict, **overrides}
    return Config.model_validate(data)

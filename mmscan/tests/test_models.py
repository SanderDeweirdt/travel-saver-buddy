import json
from pathlib import Path

import pytest

from mmscan.models import fees_eur, local_time, parse_cabin_offers, parse_trip

SYN = Path(__file__).parent / "fixtures" / "synthetic"


def avail(**fields) -> dict:
    return {"ID": "a", **fields}


def test_string_mileage_parses():
    a = avail(JAvailable=True, JMileageCost="60000", JRemainingSeats=2, JDirect=True)
    [offer] = parse_cabin_offers(a, ["business"])
    assert offer.miles == 60000
    assert offer.seats == 2
    assert offer.direct is True


@pytest.mark.parametrize("cost", ["0", "", None])
def test_unavailable_mileage_drops_cabin(cost):
    a = avail(JAvailable=True, JMileageCost=cost)
    assert parse_cabin_offers(a, ["business"]) == []


def test_available_false_with_cost_drops_cabin():
    a = avail(JAvailable=False, JMileageCost="60000")
    assert parse_cabin_offers(a, ["business"]) == []


def test_zero_seats_is_unknown():
    a = avail(YAvailable=True, YMileageCost="35000", YRemainingSeats=0)
    [offer] = parse_cabin_offers(a, ["economy"])
    assert offer.seats is None


def test_synthetic_availability_offers():
    data = json.loads((SYN / "availability.json").read_text())["data"]
    offers = parse_cabin_offers(data[0], ["economy", "business"])
    assert [(o.cabin, o.miles) for o in offers] == [("economy", 35000), ("business", 60000)]
    assert [o.cabin for o in parse_cabin_offers(data[1], ["economy", "business"])] == ["business"]


def test_parse_trip_lowercases_cabin():
    raw = json.loads((SYN / "trips.json").read_text())["data"][0]
    trip = parse_trip(raw)
    assert trip.cabin == "business"
    assert trip.miles == 60000
    assert trip.taxes_minor == 39850
    assert trip.currency == "EUR"
    assert trip.stops == 0
    assert trip.total_duration == 725
    assert trip.raw is raw


def test_parse_trip_zero_seats_unknown():
    raw = json.loads((SYN / "trips.json").read_text())["data"][1]
    assert parse_trip(raw).seats is None


def test_fees_eur():
    assert fees_eur(1290, "EUR") == 12.90
    assert fees_eur(1290, "") == 12.90
    assert fees_eur(1290, "USD") is None


def test_local_time_does_not_shift():
    assert local_time("2026-11-02T22:05:00Z") == "2026-11-02 22:05"
    assert local_time("") == ""

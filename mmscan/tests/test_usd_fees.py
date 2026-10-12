"""Live finding: lufthansa fees arrive in USD, and the summary object carries per-cabin taxes."""

import json
from datetime import UTC, datetime

import httpx
import pytest
from typer.testing import CliRunner

from mmscan.cli import app
from mmscan.client import Client
from mmscan.config import ConfigError, load_config
from mmscan.enrich import shortlist_candidates
from mmscan.models import fees_eur
from mmscan.scan import scan_watchlist
from mmscan.scoring import DEAL, SKIP, score_run
from mmscan.store import Store
from tests.helpers import avail, config, trip

NOW = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)


def _store(tmp_path, *avails, kind="region"):
    store = Store(tmp_path / "db.sqlite")
    run = store.start_run("scan", "{}", now=NOW)
    for a in avails:
        store.save_availability(run, a, kind)
    return store, run


def test_fees_eur_converts_usd_at_the_configured_rate():
    assert fees_eur(20000, "USD", 0.92) == 184.0
    assert fees_eur(20000, "USD") is None
    assert fees_eur(20000, "GBP", 0.92) is None
    assert fees_eur(20000, "EUR", 0.92) == 200.0


def test_usd_to_eur_must_be_positive(tmp_path, default_config_dict):
    (tmp_path / "c.yaml").write_text(json.dumps({**default_config_dict, "usd_to_eur": -1}))
    with pytest.raises(ConfigError, match="usd_to_eur"):
        load_config(tmp_path / "c.yaml")


def test_summary_taxes_price_a_region_result(tmp_path, default_config_dict):
    store, run = _store(tmp_path, avail("a", business=55000, taxes={"business": 20000}))
    rows, warnings = score_run(store, config(default_config_dict), run, NOW)
    [r] = rows
    assert r.fees_eur == 184.0 and r.fee_estimated is False
    assert r.total_eur == 822.0  # 638 for the miles plus 184 in fees
    assert r.verdict == DEAL  # thin data: both layers fall back to the business ceiling
    assert any("report fees in USD; converted at usd_to_eur=0.92" in w for w in warnings)


def test_without_a_rate_usd_fees_stay_unpriced(tmp_path, default_config_dict):
    store, run = _store(tmp_path, avail("a", business=55000, taxes={"business": 20000}))
    cfg = config(default_config_dict, usd_to_eur=None)
    [r], warnings = score_run(store, cfg, run, NOW)
    assert r.total_eur is None and r.fee_estimated is True and r.verdict == SKIP
    assert any("usd_to_eur is not set" in w for w in warnings)


def test_zero_summary_taxes_mean_unknown_not_free(tmp_path, default_config_dict):
    store, run = _store(tmp_path, avail("a", business=55000))
    [r], _ = score_run(store, config(default_config_dict), run, NOW)
    assert r.total_eur is None and r.fee_estimated is True


def test_stored_trips_take_precedence_over_summary(tmp_path, default_config_dict):
    store, run = _store(tmp_path, avail("a", business=55000, taxes={"business": 20000}))
    store.save_trips(
        "a",
        "2026-10-10T08:00:00Z",
        [trip("t", avail_id="a", miles=55000, taxes=30000, currency="USD")],
        None,
        {},
    )
    [r], _ = score_run(store, config(default_config_dict), run, NOW)
    assert r.fees_eur == 276.0  # 300 USD x 0.92, from the trip
    assert r.flight_numbers == "LH778"


def test_empty_trip_list_is_not_stored_as_a_fetch(tmp_path, default_config_dict):
    body = {"data": [avail("a", business=55000)], "count": 1, "hasMore": False, "cursor": 1}
    client = Client(
        "k",
        Store(tmp_path / "db.sqlite"),
        None,
        300,
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body)),
        sleep=lambda s: None,
    )
    store = client.store
    run = store.start_run("watch", "{}")
    scan_watchlist(client, store, config(default_config_dict), run, NOW.date())
    assert store.conn.execute("SELECT count(*) FROM trip_fetches").fetchone()[0] == 0
    assert store.conn.execute("SELECT count(*) FROM availabilities").fetchone()[0] == 1


def test_shortlist_candidates_skip_fetched_and_skipped(tmp_path, default_config_dict):
    cheap = avail("cheap", business=50000, taxes={"business": 15000})
    pricey = avail("pricey", origin="FRA", business=90000, taxes={"business": 90000})
    fetched = avail("fetched", origin="ZRH", business=52000, taxes={"business": 15000})
    store, run = _store(tmp_path, cheap, pricey, fetched)
    store.save_trips("fetched", fetched["UpdatedAt"], [trip("t", avail_id="fetched")], None, {})
    score_run(store, config(default_config_dict), run, NOW)
    assert shortlist_candidates(store, run) == ["cheap"]


def test_run_prices_from_summary_then_enriches_only_the_shortlist(
    tmp_path, monkeypatch, default_config_dict
):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text(json.dumps(default_config_dict))
    good = avail("good", business=55000, taxes={"business": 20000})
    pricey = avail("pricey", origin="FRA", business=95000, taxes={"business": 90000})
    seen: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path.removeprefix("/partnerapi")
        seen.append(path)
        hdr = {"X-RateLimit-Remaining": "900"}
        if path == "/availability" and req.url.params["origin_region"] == "Europe":
            return httpx.Response(200, json={"data": [good, pricey], "hasMore": False}, headers=hdr)
        if path.startswith("/trips/"):
            body = {
                "data": [
                    trip("t1", avail_id="good", miles=55000, taxes=20000).raw
                    | {
                        "ID": "t1",
                        "AvailabilityID": "good",
                        "Cabin": "Business",
                        "MileageCost": 55000,
                        "TotalTaxes": 20000,
                        "TaxesCurrency": "USD",
                        "RemainingSeats": 4,
                        "Stops": 0,
                        "FlightNumbers": "LH778",
                        "Carriers": "LH",
                    }
                ],
                "booking_links": [
                    {"label": "Book", "link": "https://book.test/x", "primary": True}
                ],
            }
            return httpx.Response(200, json=body, headers=hdr)
        return httpx.Response(200, json={"data": [], "hasMore": False}, headers=hdr)

    def from_env(cls, store, run_id, cap, **kw):
        return Client(
            "k", store, run_id, cap, transport=httpx.MockTransport(handler), sleep=lambda s: None
        )

    monkeypatch.setattr(Client, "from_env", classmethod(from_env))
    result = CliRunner().invoke(app, ["run"])
    assert result.exit_code == 0, result.output
    # 2 region pairs + 2 watchlist directions + one Get Trips for the single Shortlist result.
    assert seen.count("/availability") == 2 and seen.count("/search") == 2
    assert [p for p in seen if p.startswith("/trips/")] == ["/trips/good"]
    store = Store(tmp_path / "data" / "mmscan.db")
    rows = {r["availability_id"]: r for r in store.conn.execute("SELECT * FROM results")}
    assert rows["good"]["verdict"] == "Deal" and rows["good"]["fees_eur"] == 184.0
    assert rows["good"]["flight_numbers"] == "LH778"
    assert rows["good"]["booking_link"] == "https://book.test/x"
    assert rows["pricey"]["verdict"] == "Skip" and rows["pricey"]["flight_numbers"] is None
    assert list((tmp_path / "reports").glob("*.xlsx"))

import json
from pathlib import Path

import httpx
import pytest

from mmscan.client import ApiError, Client
from mmscan.enrich import enrich, fee_spread, select_candidates
from mmscan.store import Store
from tests.helpers import avail, config

SYN = Path(__file__).parent / "fixtures" / "synthetic"
TRIPS = json.loads((SYN / "trips.json").read_text())


def trips_body(avail_id: str, taxes: int = 39850) -> dict:
    body = json.loads(json.dumps(TRIPS))
    for t in body["data"]:
        t["AvailabilityID"] = avail_id
        t["ID"] = f"{t['ID']}-{avail_id}"
    body["data"][0]["TotalTaxes"] = taxes
    return body


def setup(tmp_path, ids, cap=300, handler=None, updated="2026-10-10T08:00:00Z"):
    store = Store(tmp_path / "db.sqlite")
    run = store.start_run("scan", "{}")
    for i, a in enumerate(ids):
        store.save_availability(
            run,
            avail(a, date=f"2026-12-{i + 1:02d}", updated=updated, business=60000 + i),
            "region",
        )
    calls = []

    def default(req):
        avail_id = req.url.path.rsplit("/", 1)[-1]
        calls.append(avail_id)
        return httpx.Response(
            200, json=trips_body(avail_id), headers={"X-RateLimit-Remaining": "900"}
        )

    client = Client(
        "k",
        store,
        run,
        cap,
        transport=httpx.MockTransport(handler or default),
        sleep=lambda s: None,
    )
    return store, run, client, calls


def test_max_calls_leaves_rest_over(tmp_path, default_config_dict):
    store, run, client, calls = setup(tmp_path, ["a", "b", "c"])
    cfg = config(default_config_dict, cabins=["business"], enrich={"max_calls": 2})
    stats = enrich(client, store, cfg, run, ["a", "b", "c"])
    assert (stats.called, stats.priced, stats.left_over) == (2, 2, 1)
    assert calls == ["a", "b"]
    link = store.conn.execute(
        "SELECT booking_link FROM trip_fetches WHERE availability_id='a'"
    ).fetchone()[0]
    assert link == "https://www.miles-and-more.com/"


def test_second_run_unchanged_makes_no_calls(tmp_path, default_config_dict):
    store, run, client, calls = setup(tmp_path, ["a", "b"])
    cfg = config(default_config_dict, cabins=["business"])
    enrich(client, store, cfg, run, ["a", "b"])
    first = len(calls)
    assert first == 2
    # Same availabilities in a new run, UpdatedAt unchanged: no candidates, no calls.
    run2 = store.start_run("scan", "{}")
    for row in store.conn.execute(
        "SELECT raw_json FROM availabilities WHERE run_id=?", (run,)
    ).fetchall():
        store.save_availability(run2, json.loads(row[0]), "region")
    candidates = select_candidates(store, cfg, run2)
    assert candidates == []
    stats = enrich(client, store, cfg, run2, candidates)
    assert len(calls) == first and stats.skipped_cached == 2


def test_changed_updated_at_refetches(tmp_path, default_config_dict):
    store, run, client, calls = setup(tmp_path, ["a"])
    cfg = config(default_config_dict, cabins=["business"])
    enrich(client, store, cfg, run, ["a"])
    run2 = store.start_run("scan", "{}")
    store.save_availability(
        run2, avail("a", updated="2026-10-11T09:00:00Z", business=60000), "region"
    )
    assert select_candidates(store, cfg, run2) == ["a"]
    enrich(client, store, cfg, run2, ["a"])
    assert calls == ["a", "a"]


def test_404_marks_expired_and_continues(tmp_path, default_config_dict):
    def handler(req):
        avail_id = req.url.path.rsplit("/", 1)[-1]
        if avail_id == "a":
            return httpx.Response(404, json={})
        return httpx.Response(200, json=trips_body(avail_id))

    store, run, client, _ = setup(tmp_path, ["a", "b"], handler=handler)
    stats = enrich(client, store, config(default_config_dict), run, ["a", "b"])
    assert (stats.expired, stats.priced) == (1, 1)
    status = store.conn.execute(
        "SELECT status FROM trip_fetches WHERE availability_id='a'"
    ).fetchone()[0]
    assert status == "expired"


def test_saved_data_survives_error_on_third_call(tmp_path, default_config_dict):
    seen = []

    def handler(req):
        avail_id = req.url.path.rsplit("/", 1)[-1]
        seen.append(avail_id)
        if len(seen) == 3:
            return httpx.Response(400, text="bad")
        return httpx.Response(200, json=trips_body(avail_id))

    store, run, client, _ = setup(tmp_path, ["a", "b", "c"], handler=handler)
    with pytest.raises(ApiError):
        enrich(client, store, config(default_config_dict), run, ["a", "b", "c"])
    fetched = {r[0] for r in store.conn.execute("SELECT availability_id FROM trip_fetches")}
    assert fetched == {"a", "b"}


def test_cap_stops_and_counts_left_over(tmp_path, default_config_dict):
    store, run, client, calls = setup(tmp_path, ["a", "b", "c"], cap=1)
    stats = enrich(client, store, config(default_config_dict), run, ["a", "b", "c"])
    assert stats.cap_reached and stats.priced == 1 and stats.left_over == 2


def test_fee_spread_matches_fixtures(tmp_path, default_config_dict):
    def handler(req):
        avail_id = req.url.path.rsplit("/", 1)[-1]
        taxes = {"a": 30000, "b": 40000, "c": 50000}[avail_id]
        return httpx.Response(200, json=trips_body(avail_id, taxes))

    store, run, client, _ = setup(tmp_path, ["a", "b", "c"], handler=handler)
    enrich(client, store, config(default_config_dict), run, ["a", "b", "c"])
    spread = {(o, d, c): rest for o, d, c, *rest in fee_spread(store)}
    assert spread[("MUC", "SIN", "business")] == [3, 300.0, 400.0, 500.0]
    assert spread[("MUC", "SIN", "economy")] == [3, 129.0, 129.0, 129.0]

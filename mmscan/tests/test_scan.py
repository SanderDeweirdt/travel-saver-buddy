import json
from datetime import date
from pathlib import Path

import httpx
from typer.testing import CliRunner

from mmscan.cli import app
from mmscan.client import Client
from mmscan.config import Config
from mmscan.scan import paginate, planned_requests, run_scan, scan_regions, scan_watchlist
from mmscan.store import Store

KEY = "pro_SECRETKEY123"
SYN = Path(__file__).parent / "fixtures" / "synthetic"
TODAY = date(2026, 10, 11)


def make(tmp_path, handler, cap=300):
    store = Store(tmp_path / "db.sqlite")
    client = Client(
        KEY, store, None, cap, transport=httpx.MockTransport(handler), sleep=lambda s: None
    )
    return client, store


def page(ids, has_more, cursor=None):
    body = {"data": [{"ID": i} for i in ids], "count": len(ids), "hasMore": has_more}
    if cursor is not None:
        body["cursor"] = cursor
    return httpx.Response(200, json=body, headers={"X-RateLimit-Remaining": "900"})


def cfg_from(default_config_dict, **overrides) -> Config:
    return Config.model_validate({**default_config_dict, **overrides})


def test_paginate_dedupes_and_follows_cursor(tmp_path):
    pages = [page(["a", "b"], True, "c1"), page(["b", "c"], False)]
    seen = []

    def handler(req):
        seen.append(dict(req.url.params))
        return pages.pop(0)

    client, _ = make(tmp_path, handler)
    items, warnings = paginate(client, "availability", {"source": "lufthansa"}, take=2)
    assert [i["ID"] for i in items] == ["a", "b", "c"]
    assert warnings == []
    assert "skip" not in seen[0] and "cursor" not in seen[0]
    assert seen[1]["skip"] == "2" and seen[1]["cursor"] == "c1"


def test_paginate_stops_on_no_new_ids(tmp_path):
    calls = []

    def handler(req):
        calls.append(1)
        return page(["a", "b"], True, "c1")

    client, _ = make(tmp_path, handler)
    items, warnings = paginate(client, "availability", {}, take=2)
    assert [i["ID"] for i in items] == ["a", "b"]
    assert len(calls) == 2
    assert len(warnings) == 1 and "no new ID" in warnings[0]


def test_two_cabins_send_no_cabin_param(tmp_path, default_config_dict):
    sent = []

    def handler(req):
        sent.append(dict(req.url.params))
        return page([], False)

    client, store = make(tmp_path, handler)
    run = store.start_run("scan", "{}")
    cfg = cfg_from(default_config_dict)
    scan_regions(client, store, cfg, run, TODAY)
    assert len(sent) == 2
    assert all("cabin" not in p for p in sent)
    assert sent[0]["origin_region"] == "Europe" and sent[0]["destination_region"] == "Asia"
    assert sent[0]["start_date"] == "2026-10-11" and sent[0]["end_date"] == "2027-09-06"
    assert sent[0]["include_filtered"] == "false" and sent[0]["min_cabin_pct"] == "100"

    sent.clear()
    scan_regions(client, store, cfg_from(default_config_dict, cabins=["business"]), run, TODAY)
    assert all(p["cabin"] == "business" for p in sent)


def test_watchlist_stores_trips_with_fees(tmp_path, default_config_dict):
    body = json.loads((SYN / "search.json").read_text())
    sent = []

    def handler(req):
        sent.append(dict(req.url.params))
        return httpx.Response(200, json=body, headers={"X-RateLimit-Remaining": "900"})

    client, store = make(tmp_path, handler)
    run = store.start_run("scan", "{}")
    cfg = cfg_from(default_config_dict)
    stats = scan_watchlist(client, store, cfg, run, TODAY)
    assert len(sent) == 2  # both directions
    assert sent[0]["origin_airport"] == ",".join(cfg.watchlist.origins)
    assert sent[1]["origin_airport"] == ",".join(cfg.watchlist.destinations)
    assert sent[0]["order_by"] == "lowest_mileage" and sent[0]["include_trips"] == "true"
    assert stats["watchlist_results"] == 2  # same ID per call, deduped within each call
    rows = store.conn.execute(
        "SELECT cabin, mileage_cost, total_taxes, taxes_currency FROM trips ORDER BY id"
    ).fetchall()
    assert [tuple(r) for r in rows] == [
        ("business", 60000, 39850, "EUR"),
        ("economy", 35000, 12900, ""),
    ]
    fetch = store.conn.execute("SELECT status, updated_at FROM trip_fetches").fetchone()
    assert tuple(fetch) == ("ok", "2026-10-10T08:00:00Z")
    kind = store.conn.execute("SELECT origin_kind FROM availabilities").fetchone()[0]
    assert kind == "watchlist"


def test_dry_run_sends_nothing_and_lists_requests(tmp_path, monkeypatch, default_config_dict):
    reqs = planned_requests(cfg_from(default_config_dict), TODAY)
    assert [p for p, _ in reqs] == ["availability", "availability", "search", "search"]
    assert all(params["take"] == 1000 for _, params in reqs)

    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text(json.dumps(default_config_dict))
    result = CliRunner().invoke(app, ["scan", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "Would start with 4 requests" in result.output
    assert not (tmp_path / "data").exists()


def test_cap_mid_scan_marks_run_partial(tmp_path, default_config_dict):
    pages = [page(["a", "b"], True, "c1"), page(["c"], True)]

    def handler(req):
        return pages.pop(0)

    client, store = make(tmp_path, handler, cap=2)
    run = store.start_run("scan", "{}")
    status, stats = run_scan(client, store, cfg_from(default_config_dict), run, TODAY)
    assert status == "partial"
    assert stats["region_results"] == 3  # both pages kept
    assert stats["calls"] == 2
    row = store.conn.execute("SELECT status, warnings_json FROM runs WHERE id=?", (run,)).fetchone()
    assert row["status"] == "partial"
    assert "daily_call_cap" in row["warnings_json"]


def test_quota_reads_last_header(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = Store(tmp_path / "data" / "mmscan.db")
    store.record_call(None, "/availability", {}, 200, 5, 10, 812)
    store.close()
    result = CliRunner().invoke(app, ["quota"])
    assert result.exit_code == 0, result.output
    assert "812" in result.output
    assert "1 of cap 300" in result.output


def test_repo_config_also_scans_flights_within_asia():
    from pathlib import Path

    from mmscan.config import load_config
    from mmscan.scan import region_requests

    cfg = load_config(Path(__file__).resolve().parents[1] / "config.yaml")
    pairs = {(p["origin_region"], p["destination_region"]) for _, p in region_requests(cfg, TODAY)}
    assert pairs == {("Europe", "Asia"), ("Asia", "Europe"), ("Asia", "Asia")}


def test_repo_config_asks_star_alliance_programs_for_flights_within_asia():
    from pathlib import Path

    from mmscan.config import load_config
    from mmscan.scan import region_requests

    cfg = load_config(Path(__file__).resolve().parents[1] / "config.yaml")
    all_reqs = [p for _, p in region_requests(cfg, TODAY)]
    reqs = [p for p in all_reqs if p["origin_region"] == p["destination_region"]]
    sources = {p["source"] for p in reqs}
    assert "singapore" in sources and "lufthansa" not in sources
    assert len(reqs) == len(sources)
    europe = [p["source"] for p in all_reqs if p["origin_region"] != p["destination_region"]]
    assert set(europe) == {"lufthansa"}


def test_a_rejected_source_is_skipped_and_the_others_still_run(tmp_path, default_config_dict):
    default_config_dict["region_pairs"] = [
        {"origin": "Asia", "destination": "Asia", "sources": ["aeroplan", "bogus", "united"]}
    ]
    sent = []

    def handler(req):
        src = req.url.params["source"]
        sent.append(src)
        if src == "bogus":
            return httpx.Response(400, json={"error": True, "code": "invalid_source"})
        return page([f"id-{src}"], False)

    client, store = make(tmp_path, handler)
    run = store.start_run("scan", "{}")
    stats = scan_regions(client, store, cfg_from(default_config_dict), run, TODAY)
    assert sent[0] == "aeroplan" and sent[-1] == "united" and "bogus" in sent
    assert stats["region_results"] == 2
    assert any("Skipped bogus" in w for w in stats["warnings"])

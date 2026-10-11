import json
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
from typer.testing import CliRunner

from mmscan.cli import app
from mmscan.client import Client
from mmscan.scan import paginate, run_scan
from mmscan.scoring import score_run
from mmscan.store import Store
from tests.helpers import avail, config, trip

NOW = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)
SYN = Path(__file__).parent / "fixtures" / "synthetic"


def page(ids, has_more):
    return httpx.Response(
        200, json={"data": [{"ID": i} for i in ids], "hasMore": has_more, "cursor": 1}
    )


def test_paginate_stops_at_max_pages(tmp_path):
    calls = []

    def handler(req):
        calls.append(1)
        return page([f"x{len(calls)}"], True)

    store = Store(tmp_path / "db.sqlite")
    client = Client(
        "k", store, None, 300, transport=httpx.MockTransport(handler), sleep=lambda s: None
    )
    items, warnings = paginate(client, "search", {}, take=10, max_pages=1)
    assert len(calls) == 1 and [i["ID"] for i in items] == ["x1"] and warnings == []


def test_watch_only_scans_watchlist_one_page_each(tmp_path, default_config_dict):
    body = json.loads((SYN / "search.json").read_text())
    body["hasMore"] = True
    paths = []

    def handler(req):
        paths.append(req.url.path)
        return httpx.Response(200, json=body)

    store = Store(tmp_path / "db.sqlite")
    run = store.start_run("watch", "{}")
    client = Client(
        "k", store, run, 300, transport=httpx.MockTransport(handler), sleep=lambda s: None
    )
    status, stats = run_scan(
        client, store, config(default_config_dict), run, date(2026, 10, 11), watch_only=True
    )
    assert status == "ok"
    assert paths == ["/partnerapi/search", "/partnerapi/search"]
    assert stats["region_results"] == 0 and stats["watchlist_trips"] == 2


def _scored_run(store, cfg, kind, ids_taxes):
    run = store.start_run(kind, "{}", now=NOW)
    for i, (avail_id, taxes) in enumerate(ids_taxes.items()):
        store.save_availability(
            run, avail(avail_id, date=f"2026-12-{i + 1:02d}", business=60000), "watchlist"
        )
        store.save_trips(
            avail_id, "2026-10-10T08:00:00Z", [trip(f"t{avail_id}{run}", taxes=taxes)], None, {}
        )
    rows, _ = score_run(store, cfg, run, NOW)
    return run, {s.availability_id: s.change for s in rows}


def test_change_uses_last_seen_across_run_kinds(tmp_path, default_config_dict):
    cfg = config(default_config_dict, cabins=["business"])
    store = Store(tmp_path / "db.sqlite")
    # Daily full run sees a and b.
    _scored_run(store, cfg, "run", {"a": 40000, "b": 40000})
    # Hourly watch sees only a: no change, nothing New.
    _, ch = _scored_run(store, cfg, "watch", {"a": 40000})
    assert ch == {"a": ""}
    # Next full run sees b again: still not New, even though the previous run lacked it.
    _, ch = _scored_run(store, cfg, "run", {"a": 40000, "b": 40000, "c": 40000})
    assert ch == {"a": "", "b": "", "c": "New"}
    # A drop is Cheaper once, then quiet at the same price.
    _, ch = _scored_run(store, cfg, "watch", {"a": 1000})
    assert ch == {"a": "Cheaper"}
    _, ch = _scored_run(store, cfg, "watch", {"a": 1000})
    assert ch == {"a": ""}


def test_full_run_commands_ignore_watch_runs(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    full = store.start_run("scan", "{}")
    watch = store.start_run("watch", "{}")
    store.save_availability(full, avail("a", business=60000), "region")
    store.save_availability(watch, avail("b", business=60000), "watchlist")
    assert store.latest_scanned_run(("scan", "run")) == full
    assert store.latest_scanned_run() == watch


def test_watch_dry_run(tmp_path, monkeypatch, default_config_dict):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text(json.dumps(default_config_dict))
    result = CliRunner().invoke(app, ["watch", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "Planned calls: at most 2" in result.output
    assert result.output.count("GET /search") == 2
    assert not (tmp_path / "data").exists()

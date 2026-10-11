import json

import httpx

from mmscan.check import planned_check_requests, run_check
from mmscan.client import Client
from mmscan.store import Store

KEY = "pro_SECRETKEY123"


def handler(req: httpx.Request) -> httpx.Response:
    h = {"X-RateLimit-Remaining": "996"}
    if req.url.path.endswith("/availability"):
        body = {"data": [{"ID": "av1", "note": f"echo {KEY}"}], "hasMore": False, "cursor": 1}
    elif req.url.path.endswith("/trips/av1"):
        body = {"data": [{"ID": "t1", "TotalTaxes": 1290}], "booking_links": []}
    else:
        body = {"data": [], "count": 0, "hasMore": False, "cursor": 2}
    return httpx.Response(200, json=body, headers=h)


def test_check_writes_four_fixtures_without_key(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    client = Client(KEY, store, None, 300, transport=httpx.MockTransport(handler))
    paths = run_check(client, tmp_path / "live", KEY)
    names = sorted(p.name for p in paths)
    assert names == ["availability.json", "search.json", "search_minified.json", "trips.json"]
    assert store.calls_today() == 4
    for p in paths:
        text = p.read_text()
        assert KEY not in text
    saved = json.loads((tmp_path / "live" / "availability.json").read_text())
    assert saved["request"]["params"]["origin_region"] == "Europe"
    assert saved["headers"]["X-RateLimit-Remaining"] == "996"
    assert "REDACTED" in json.dumps(saved["body"])
    trips = json.loads((tmp_path / "live" / "trips.json").read_text())
    assert trips["request"]["endpoint"] == "/trips/av1"
    minified = json.loads((tmp_path / "live" / "search_minified.json").read_text())
    assert minified["request"]["params"]["minify_trips"] is True


def test_dry_run_lists_four_requests():
    reqs = planned_check_requests()
    assert [r[0] for r in reqs] == ["availability", "trips/{first ID}", "search", "search"]
    assert reqs[0][1] == {
        "source": "lufthansa",
        "cabin": "business",
        "origin_region": "Europe",
        "destination_region": "Asia",
        "take": 10,
    }
    assert reqs[2][1]["include_trips"] is True and "minify_trips" not in reqs[2][1]

from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from mmscan.scoring import score_run
from mmscan.store import Store
from mmscan.web.app import create_app
from mmscan.web.auth import MAX_FAILURES, LoginLimiter, password_ok
from mmscan.web.settings import SettingsError, WebSettings, settings_from_env
from tests.helpers import avail, config, trip

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "correct horse"
NOW = datetime.now(UTC)


@pytest.fixture
def db(tmp_path, default_config_dict):
    """A SQLite store with three scored watch runs on MUC-SIN business."""
    cfg = config(default_config_dict, relative={"percentile_good": 20, "min_samples": 2})
    path = tmp_path / "web.db"
    store = Store(path)
    for days, miles in ((2, 70000), (1, 64000), (0, 58000)):
        at = NOW - timedelta(days=days)
        run = store.start_run("watch", "{}", now=at)
        store.save_availability(run, avail(f"a{days}", business=miles), "watchlist")
        store.save_trips(
            f"a{days}",
            "2026-10-10T08:00:00Z",
            [trip(f"t{days}", avail_id=f"a{days}", miles=miles, taxes=30000)],
            "https://example.test/book",
            {},
        )
        score_run(store, cfg, run, at)
        store.record_call(run, "/search", {}, 200, 5, 1, 880 + days, now=at)
        store.finish_run(run, "partial" if days == 1 else "ok", {}, [], now=at)
    store.close()
    return path


@pytest.fixture
def client(db):
    settings = WebSettings(PASSWORD, "s" * 32, db, ROOT / "config.yaml", secure_cookies=True)
    return TestClient(create_app(settings), base_url="https://testserver")


def login(c: TestClient, password: str = PASSWORD):
    return c.post("/login", data={"password": password}, follow_redirects=False)


def test_healthz_is_public(client):
    assert client.get("/healthz").text == "ok"


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/runs",
        "/trips",
        "/quota",
        "/route/MUC/SIN/business",
        "/reports/latest.xlsx",
        "/reports/latest-shortlist.csv",
    ],
)
def test_anonymous_requests_are_redirected_to_login(client, path):
    r = client.get(path, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/login")


def test_wrong_password_fails_and_right_one_works(client):
    r = login(client, "nope")
    assert r.status_code == 401
    assert client.get("/runs", follow_redirects=False).status_code == 303
    r = login(client)
    assert r.status_code == 303 and r.headers["location"] == "/"
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "secure" in cookie and "samesite=lax" in cookie
    assert client.get("/runs").status_code == 200


def test_login_does_not_redirect_off_site(client):
    r = client.post(
        "/login", data={"password": PASSWORD, "next": "//evil.test"}, follow_redirects=False
    )
    assert r.headers["location"] == "/"


def test_logout_ends_the_session(client):
    login(client)
    client.post("/logout")
    assert client.get("/", follow_redirects=False).status_code == 303


def test_login_is_rate_limited(client):
    for _ in range(MAX_FAILURES):
        assert login(client, "x").status_code == 401
    r = login(client)  # even the right password waits
    assert r.status_code == 200 and "Too many attempts" in r.text


def test_limiter_window_and_compare():
    t = [0.0]
    lim = LoginLimiter(clock=lambda: t[0])
    for _ in range(MAX_FAILURES):
        lim.fail("c")
    assert lim.blocked("c")
    t[0] = 10_000
    assert not lim.blocked("c")
    assert password_ok("a", "a") and not password_ok("a", "b")


def test_shortlist_page_shows_fixture_data(client):
    login(client)
    r = client.get("/")
    assert r.status_code == 200
    assert "Cached data. Confirm price and seats on miles-and-more.com" in r.text
    assert "MUC→SIN" in r.text and "58,000" in r.text
    assert "https://example.test/book" in r.text
    # filters narrow the table
    assert "58,000" not in client.get("/?cabin=economy").text
    assert "Nothing matches" in client.get("/?route=FRA-KUL").text


def test_route_runs_quota_pages(client):
    login(client)
    r = client.get("/route/MUC/SIN/business")
    assert r.status_code == 200 and "<svg" in r.text and "Table view" in r.text
    runs = client.get("/runs").text
    assert 'class="partial"' in runs  # the partial run is highlighted
    q = client.get("/quota").text
    assert "of 300 calls used today" in q and "880" in q


def test_report_downloads(client):
    login(client)
    r = client.get("/reports/latest.xlsx")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    wb = load_workbook(BytesIO(r.content))
    assert "Shortlist" in wb.sheetnames
    r = client.get("/reports/latest-shortlist.csv")
    assert r.status_code == 200 and r.text.startswith("Verdict,")


def test_no_endpoint_triggers_a_scan(client):
    login(client)
    for path in ("/scan", "/run", "/watch"):
        assert client.post(path).status_code in (404, 405)


def test_empty_database_renders(tmp_path):
    settings = WebSettings(PASSWORD, "s" * 32, tmp_path / "e.db", ROOT / "config.yaml")
    c = TestClient(create_app(settings), base_url="https://testserver")
    login(c)
    assert "No scored run yet" in c.get("/").text
    assert c.get("/reports/latest.xlsx").status_code == 404


def test_refuses_to_start_without_secrets(monkeypatch):
    monkeypatch.delenv("DASHBOARD_PASSWORD", raising=False)
    monkeypatch.setenv("SESSION_SECRET", "x")
    with pytest.raises(SettingsError, match="DASHBOARD_PASSWORD"):
        settings_from_env()
    monkeypatch.setenv("DASHBOARD_PASSWORD", "p")
    monkeypatch.delenv("SESSION_SECRET")
    with pytest.raises(SettingsError, match="SESSION_SECRET"):
        settings_from_env()


def test_trips_page_without_trips_explains_setup(client):
    login(client)
    r = client.get("/trips")
    assert r.status_code == 200 and "No trips configured" in r.text


def test_trips_page_lists_pairs(tmp_path, default_config_dict, write_config):
    from tests.test_trips import LEGS, TRIP, add_run
    from tests.test_trips import NOW as T_NOW

    cfg_path = write_config({**default_config_dict, "trips": [TRIP]})
    path = tmp_path / "trips.db"
    store = Store(path)
    add_run(store, config(default_config_dict, trips=[TRIP]), LEGS, at=T_NOW)
    store.close()
    c = TestClient(
        create_app(WebSettings(PASSWORD, "s" * 32, path, cfg_path, secure_cookies=True)),
        base_url="https://testserver",
    )
    login(c)
    text = c.get("/trips").text
    assert "Family stay" in text and "2027-06-10" in text and "2027-08-25" in text
    assert "Cheapest for 2" in text and "pairs" in text


def test_shortlist_labels_dynamic_prices(tmp_path, default_config_dict):
    cfg = config(default_config_dict, relative={"percentile_good": 20, "min_samples": 2})
    path = tmp_path / "mix.db"
    store = Store(path)
    run = store.start_run("watch", "{}", now=NOW)
    for aid, airlines in (("fx", "SQ"), ("dyn", "LH")):
        store.save_availability(run, avail(aid, airlines=airlines, business=60000), "watchlist")
        store.save_trips(
            aid,
            "2026-10-10T08:00:00Z",
            [trip(f"t{aid}", avail_id=aid, miles=60000, taxes=30000, carriers=airlines)],
            None,
            {},
        )
    score_run(store, cfg, run, NOW)
    store.close()
    settings = WebSettings(PASSWORD, "s" * 32, path, ROOT / "config.yaml")
    c = TestClient(create_app(settings), base_url="https://testserver")
    login(c)
    page = c.get("/?all=1").text
    assert "dynamic, verify" in page and ">chart<" in page
    assert ">Unranked</span>" in page  # the dynamic fare has no history yet
    assert ">Unranked</span>" not in c.get("/").text  # and never reaches the Shortlist

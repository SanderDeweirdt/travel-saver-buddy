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
    """A SQLite store with three scored scan runs on MUC-SIN business."""
    cfg = config(default_config_dict, relative={"percentile_good": 20, "min_samples": 2})
    path = tmp_path / "web.db"
    store = Store(path)
    for days, miles in ((2, 70000), (1, 64000), (0, 58000)):
        at = NOW - timedelta(days=days)
        run = store.start_run("scan", "{}", now=at)
        store.save_availability(run, avail(f"a{days}", business=miles), "watchlist")
        store.save_trips(
            f"a{days}",
            "2026-10-10T08:00:00Z",
            [trip(f"t{days}", avail_id=f"a{days}", miles=miles, taxes=30000)],
            "https://example.test/book",
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
        "/watchlist",
        "/runs",
        "/quota",
        "/settings",
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


def test_route_runs_quota_pages(client):
    login(client)
    r = client.get("/route/MUC/SIN/business")
    assert r.status_code == 200 and "<svg" in r.text and "Table view" in r.text
    runs = client.get("/runs").text
    assert 'class="partial"' in runs  # the partial run is highlighted
    q = client.get("/quota").text
    assert "of 800 calls used today" in q and "880" in q


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


def test_refuses_to_start_without_secrets(monkeypatch):
    monkeypatch.delenv("DASHBOARD_PASSWORD", raising=False)
    monkeypatch.setenv("SESSION_SECRET", "x")
    with pytest.raises(SettingsError, match="DASHBOARD_PASSWORD"):
        settings_from_env()
    monkeypatch.setenv("DASHBOARD_PASSWORD", "p")
    monkeypatch.delenv("SESSION_SECRET")
    with pytest.raises(SettingsError, match="SESSION_SECRET"):
        settings_from_env()


def test_deals_view_reads_the_store(db, default_config_dict):
    from mmscan.web import queries

    cfg = config(default_config_dict, relative={"percentile_good": 20, "min_samples": 2})
    store = Store(db)
    view = queries.deals_view(store, cfg, NOW, pax=2, hide_stale=False)
    store.close()
    # one flight date seen three times is one observation: too little history for a baseline
    assert view["deals"] == [] and len(view["building"]) == 1
    assert view["thin_routes"] == 1 and view["total"] >= 1


@pytest.fixture
def deals_client(tmp_path, default_config_dict, write_config):
    """Eight flight dates on MUC-SIN business; the newest run holds the cheapest one."""
    cfg = config(default_config_dict, relative={"percentile_good": 20, "min_samples": 3})
    path = tmp_path / "deals.db"
    store = Store(path)
    at = NOW - timedelta(hours=1)
    run = store.start_run("scan", "{}", now=at)
    prices = [70000, 68000, 66000, 64000, 62000, 60000, 58000, 36000]
    for i, miles in enumerate(prices):
        aid = f"d{i}"
        store.save_availability(
            run,
            avail(aid, date=f"2026-12-1{i}", business=miles, updated=at.isoformat()),
            "watchlist",
        )
        store.save_trips(
            aid,
            at.isoformat(),
            [trip(f"t{i}", avail_id=aid, miles=miles, taxes=30000)],
            "https://example.test/book",
        )
    score_run(store, cfg, run, at)
    store.finish_run(run, "ok", {}, [], now=at)
    store.finish_run(store.start_run("watch", "{}", now=at), "ok", {}, [], now=at)
    store.close()
    cfg_path = write_config(
        {**default_config_dict, "relative": {"percentile_good": 20, "min_samples": 3}}
    )
    settings = WebSettings(PASSWORD, "s" * 32, path, cfg_path, secure_cookies=True)
    c = TestClient(create_app(settings), base_url="https://testserver")
    login(c)
    return c


def test_route_page_shows_usual_price_and_saving(deals_client):
    r = deals_client.get("/route/MUC/SIN/business")
    assert r.status_code == 200
    assert "Usual price" in r.text and "Best now vs usual" in r.text
    assert "Great deal" in r.text
    assert 'class="usual"' in r.text  # dashed line on the chart


def test_route_page_with_thin_history_says_so(db):
    settings = WebSettings(PASSWORD, "s" * 32, db, ROOT / "config.yaml", secure_cookies=True)
    c = TestClient(create_app(settings), base_url="https://testserver")
    login(c)
    r = c.get("/route/MUC/SIN/business")
    assert r.status_code == 200 and "building history" in r.text
    assert 'class="usual"' not in r.text


def test_price_chart_draws_usual_line():
    from mmscan.web.charts import price_chart

    pts = [{"ts": "2026-10-01T00:00:00Z", "low": 500.0, "median": 700.0, "n": 3}]
    assert 'class="usual"' in price_chart(pts, 900.0)
    assert 'class="usual"' not in price_chart(pts)


def _trips_client(tmp_path, default_config_dict, write_config, trip_extra=None, days=(0,)):
    from datetime import timedelta as td

    from tests.test_trips import LEGS, TRIP, add_run
    from tests.test_trips import NOW as T_NOW

    trip_cfg = {**TRIP, **(trip_extra or {})}
    cfg_path = write_config({**default_config_dict, "trips": [trip_cfg]})
    path = tmp_path / "trips2.db"
    store = Store(path)
    cfg = config(default_config_dict, trips=[trip_cfg])
    for back in days:  # days ago, oldest first
        add_run(store, cfg, LEGS, at=T_NOW - td(days=back))
    store.close()
    c = TestClient(
        create_app(WebSettings(PASSWORD, "s" * 32, path, cfg_path, secure_cookies=True)),
        base_url="https://testserver",
    )
    login(c)
    return c


def test_data_page(deals_client):
    text = deals_client.get("/settings").text
    assert "Data &amp; alerts" in text and "API calls today" in text
    assert "How far to trust cached miles" in text and "not checked yet" in text  # LH etc.
    assert "Slack alerts" in text and "not sent" in text  # dynamic prices off by default
    assert "Healthy" in text or "Late" in text
    assert "Database size" in text and "/ 5<" not in text and "GB" in text


def test_data_page_shows_manual_price_checks(db, default_config_dict):
    store = Store(db)
    store.add_price_check("lh", 6000, 17000, "MUC-SIN", "business")
    store.add_price_check("LH", 10000, 12000)
    store.close()
    c = TestClient(
        create_app(WebSettings(PASSWORD, "s" * 32, db, ROOT / "config.yaml", secure_cookies=True)),
        base_url="https://testserver",
    )
    login(c)
    text = c.get("/settings").text
    assert "2.02×" in text  # median of 2.83 and 1.2
    assert "1.20× to 2.83×" in text


def test_usd_rate_warning_when_old(default_config_dict):
    from datetime import date

    from mmscan.scoring import _currency_warnings

    old = config(default_config_dict, usd_to_eur=0.92, usd_to_eur_date=date(2020, 1, 1))
    assert any("last checked" in w for w in _currency_warnings({"USD": 3}, old))
    fresh = config(default_config_dict, usd_to_eur=0.92, usd_to_eur_date=date.today())
    assert not any("last checked" in w for w in _currency_warnings({"USD": 3}, fresh))
    assert old.usd_rate_age_days(date(2020, 2, 1)) == 31


def test_all_routes_lists_every_flight_not_one_per_route(deals_client):
    r = deals_client.get("/overview?cabin=all&fresh=0&pax=1")
    assert r.status_code == 200
    assert r.text.count("MUC→SIN") == 8  # eight dates, one row each
    assert "Nothing matches" in deals_client.get("/overview?fresh=0").text  # default cabin economy
    assert (
        "Nothing matches"
        in deals_client.get("/overview?cabin=all&direction=Asia+%E2%86%92+Europe").text
    )


def test_overview_filters_by_region_or_airport(deals_client):
    base = "/overview?cabin=all&fresh=0&pax=1"
    assert deals_client.get(base + "&origin=MUC&destination=SIN").text.count("MUC→SIN") == 8
    assert deals_client.get(base + "&origin=Europe&destination=Asia").text.count("MUC→SIN") == 8
    assert (
        deals_client.get(base + "&origin=Europe&destination=southeast_asia").text.count("MUC→SIN")
        == 8
    )
    for q in ("origin=FRA", "destination=KUL", "origin=Asia", "destination=Europe"):
        assert "Nothing matches" in deals_client.get(f"{base}&{q}").text
    page = deals_client.get(base).text
    assert 'name="origin"' in page and 'name="destination"' in page and "combo-list" in page
    assert 'name="direction"' not in page and 'name="route"' not in page


def test_hide_chart_deals_toggle(deals_client):
    assert "Nothing matches" in deals_client.get("/overview?cabin=all&fresh=0&nochart=1").text
    assert "MUC→SIN" in deals_client.get("/overview?cabin=all&fresh=0&chart=1").text
    both = deals_client.get("/overview?cabin=all&fresh=0&chart=1&nochart=1").text
    assert "Nothing matches" in both  # hide wins over chart-only


def test_every_row_links_to_miles_and_more(default_config_dict):
    from mmscan.config import load_config
    from mmscan.links import mm_link
    from tests.helpers import scored

    cfg = config(
        default_config_dict,
        miles_and_more=load_config(ROOT / "config.yaml").miles_and_more.model_dump(),
    )
    s = scored(400, origin="MUC", dest="FRA", date="2026-10-16", cabin="business")
    assert mm_link(cfg, s) == (
        "https://www.miles-and-more.com/row/en/spend/flights/flight-award.html?adults=1"
        "&bookingclass=B&children=0&dateformat=MM%2Fdd%2Fyyyy&destinationcode=FRA&infants=0"
        "&l=GB&origincode=MUC&outbounddate=10%2F16%2F2026&travellertype=M&triptype=OW&youths=0"
    )
    assert "adults=3" in mm_link(cfg, s, pax=3)
    assert "bookingclass=E" in mm_link(cfg, scored(400, cabin="economy"))
    assert mm_link(cfg, scored(400, cabin="premium"), 1) is None  # no known booking class
    s.booking_link = "https://stored.test/x"
    assert mm_link(cfg, s) == "https://stored.test/x"  # seats.aero's own link wins
    off = config(default_config_dict, miles_and_more={"link_template": ""})
    assert mm_link(off, scored(400)) is None  # no template


def test_link_template_rejects_unknown_placeholders(default_config_dict):
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        config(default_config_dict, miles_and_more={"link_template": "https://x/{nope}"})


def test_row_limit_and_show_more(deals_client):
    page = deals_client.get("/overview?cabin=all&fresh=0&pax=1&limit=50").text
    assert "Showing the first" not in page  # only 8 flights, under the limit
    r = deals_client.get("/overview?cabin=all&fresh=0&pax=1&limit=-5")
    assert r.status_code == 200  # a bad limit is clamped, not an error


def test_deals_pages_show_a_newer_watch_price_without_a_run_label(db, default_config_dict):
    store = Store(db)
    run = store.start_run("watch", "{}", now=NOW + timedelta(hours=1))
    store.save_availability(
        run, avail("w1", taxes={"business": 30000}, business=50000), "watchlist"
    )
    cfg = config(default_config_dict, relative={"percentile_good": 20, "min_samples": 2})
    score_run(store, cfg, run, NOW + timedelta(hours=1))
    store.finish_run(run, "ok", {}, [], now=NOW + timedelta(hours=1))
    store.close()
    c = TestClient(
        create_app(WebSettings(PASSWORD, "s" * 32, db, ROOT / "config.yaml", secure_cookies=True)),
        base_url="https://testserver",
    )
    login(c)
    text = c.get("/overview?cabin=all&fresh=0&pax=1").text
    assert "Run #" not in text  # pages no longer belong to one run
    # Same flight date as the fixture's: the watch run's price replaces the older 58,000.
    assert "MUC→SIN" in text and "50,000" in text and "58,000" not in text


def test_data_page_shows_routes_tracked(client):
    login(client)
    text = client.get("/settings").text
    assert "Routes tracked" in text and "airport pairs with a price" in text
    assert "flights on offer" in text


def _settings_form(**over):
    form = {
        "mile_cost_eur_cents": "1.2",
        "mr_point_value_eur_cents": "0.8",
        "bookable__singapore": "on",
        "mr__singapore": "1.5",
        "cost__aeroplan": "1.4",
    }
    form.update(over)
    return {k: v for k, v in form.items() if v is not None}


def test_settings_rejects_bad_input_and_keeps_the_old_values(client, db):
    login(client)
    r = client.post("/settings", data=_settings_form(mile_cost_eur_cents="abc"))
    assert r.status_code == 422 and "not a number" in r.text
    r = client.post("/settings", data=_settings_form(mr_point_value_eur_cents=""))
    assert r.status_code == 422 and "mr_point_value_eur_cents" in r.text
    r = client.post("/settings", data=_settings_form(mile_cost_eur_cents="0"))
    assert r.status_code == 422
    assert Store(db, readonly=True).get_overrides() == {}


def test_empty_database_renders(tmp_path):
    settings = WebSettings(PASSWORD, "s" * 32, tmp_path / "e.db", ROOT / "config.yaml")
    c = TestClient(create_app(settings), base_url="https://testserver")
    login(c)
    assert "No prices yet" in c.get("/overview").text
    assert c.get("/reports/latest.xlsx").status_code == 404


def test_settings_page_saves_what_you_enter(client, db):
    login(client)
    page = client.get("/settings")
    assert page.status_code == 200 and "Amex Membership Rewards point" in page.text
    assert "bookable__singapore" in page.text and 'name="bookable__lufthansa"' not in page.text
    assert "Reset" not in page.text  # one source of truth: no way back to config.yaml

    r = client.post("/settings", data=_settings_form(), follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/settings?saved=1"
    saved = Store(db, readonly=True).get_overrides()
    assert saved["mr_point_value_eur_cents"] == 0.8
    assert saved["programs"]["singapore"]["enabled"] is True
    assert saved["programs"]["aeroplan"]["enabled"] is False  # unticked
    assert saved["programs"]["singapore"]["mr_per_mile"] == 1.5
    after = client.get("/settings?saved=1").text
    assert 'value="0.8"' in after and "Saved." in after
    # a new process reads the same settings from the database
    fresh = TestClient(
        create_app(WebSettings(PASSWORD, "s" * 32, db, ROOT / "config.yaml")),
        base_url="https://testserver",
    )
    login(fresh)
    assert 'value="0.8"' in fresh.get("/settings").text

    # ticked stays ticked, and a program left unticked in the form is off afterwards
    assert 'name="bookable__singapore" id="b-singapore" checked' in after
    assert 'name="bookable__flyingblue" id="b-flyingblue" checked' not in after


def test_overview_survives_bad_params(deals_client):
    assert deals_client.get("/overview?sort=bogus&pax=0").status_code == 200
    assert deals_client.get("/overview?pax=99").status_code == 200


def test_settings_page_edits_within_asia_and_the_other_config_fields(client, db):
    login(client)
    page = client.get("/settings").text
    assert 'name="within__aeroplan"' in page and 'name="f__fx_to_eur"' in page
    assert "SGD = 0.67" in page and "Europe &gt; Asia" in page
    form = _settings_form(
        withinseen__singapore="1",  # unticked: off within Asia
        withinseen__aeroplan="1",
        within__aeroplan="on",
        f__min_seats="3",
        f__date_window__end_offset_days="120",
        f__fx_to_eur="SGD = 0.7\nTHB = 0.03",
        f__region_pairs="Europe > Asia\nAsia > Asia",
    )
    form["f__date_window.end_offset_days"] = form.pop("f__date_window__end_offset_days")
    r = client.post("/settings", data=form, follow_redirects=False)
    assert r.status_code == 303
    saved = Store(db, readonly=True).get_overrides()
    assert saved["programs"]["singapore"]["within_region"] is False
    assert saved["programs"]["aeroplan"]["within_region"] is True
    assert saved["min_seats"] == 3 and saved["date_window"] == {"end_offset_days": 120}
    assert saved["fx_to_eur"] == {"SGD": 0.7, "THB": 0.03}
    assert len(saved["region_pairs"]) == 2
    bad = client.post("/settings", data=_settings_form(**{"f__fx_to_eur": "SGD 0.7"}))
    assert bad.status_code == 422 and "should look like" in bad.text


def test_settings_page_edits_benchmarks_and_slack_alerts(client, db):
    login(client)
    page = client.get("/settings").text
    assert 'name="bm__0__name" value="economy_europe_southeast_asia"' in page
    assert 'name="bm__2__name" value=""' in page  # the empty row to add one
    assert 'name="f__notify.new_deals.min_pct"' in page
    form = _settings_form(
        bm_seen="1",
        bm__0__name="economy_europe_southeast_asia",
        bm__0__cabin="economy",
        bm__0__from="Europe",
        bm__0__to="southeast_asia",
        bm__0__good_miles_max="30000",
        bm__0__chart_rate_miles="42500",
        bm__0__fees_max_eur="280",
        bm__1__name="business_europe_southeast_asia",
        bm__1__remove="on",
        bm__2__name="eco_asia",
        bm__2__cabin="economy",
        bm__2__from="Asia",
        bm__2__to="Asia",
        bm__2__good_miles_max="9000",
        bm__2__chart_rate_miles="15000",
        bm__2__fees_max_eur="60",
    )
    form["f__notify.new_deals.min_pct"] = "25"
    form["f__notify.new_deals.enabled__seen"] = "1"  # unticked: off
    form["f__notify.slack"] = "on"
    form["f__notify.slack__seen"] = "1"
    r = client.post("/settings", data=form, follow_redirects=False)
    assert r.status_code == 303, r.text
    saved = Store(db, readonly=True).get_overrides()
    assert [b["name"] for b in saved["benchmarks"]] == ["economy_europe_southeast_asia", "eco_asia"]
    assert saved["benchmarks"][0]["good_miles_max"] == 30000
    assert saved["notify"] == {"new_deals": {"min_pct": 25.0, "enabled": False}, "slack": True}
    bad = client.post("/settings", data={**form, "bm__2__good_miles_max": "x"})
    assert bad.status_code == 422 and "not a number" in bad.text


def _add(client, **over):
    form = {
        "origin": "muc",
        "destination": "SIN",
        "date_from": "2026-12-01",
        "date_to": "2026-12-31",
    }
    return client.post("/watchlist", data={**form, **over}, follow_redirects=False)


def test_watchlist_starts_empty_and_old_url_still_works(client):
    login(client)
    text = client.get("/watchlist").text
    assert "<h1>Flight watchlist</h1>" in text and "Nothing on the watchlist yet" in text
    assert client.get("/shortlist").status_code == 200


def test_watchlist_item_can_be_added_listed_opened_and_removed(client, db):
    login(client)
    r = _add(client)
    assert r.status_code == 303 and r.headers["location"] == "/watchlist?added=1"
    item = Store(db, readonly=True).watch_items()[0]
    assert (item["origin"], item["destination"]) == ("MUC", "SIN")  # codes are upper-cased
    listing = client.get("/watchlist").text
    assert "MUC→SIN" in listing and "2026-12-01 to 2026-12-31" in listing
    assert f'href="/watchlist/{item["id"]}"' in listing
    detail = client.get(f"/watchlist/{item['id']}")
    assert detail.status_code == 200 and "58,000" in detail.text  # the fixture flight fits
    r = client.post(f"/watchlist/{item['id']}/delete", follow_redirects=False)
    assert r.status_code == 303
    assert Store(db, readonly=True).watch_items() == []
    assert client.get(f"/watchlist/{item['id']}").status_code == 404


def test_watchlist_detail_only_shows_flights_inside_the_filters(client, db):
    login(client)
    _add(client, date_from="2027-01-01", date_to="")  # a single day with no flights
    _add(client, destination="KUL")  # a different airport
    items = Store(db, readonly=True).watch_items()
    for i in items:
        text = client.get(f"/watchlist/{i['id']}").text
        assert "58,000" not in text and "No flights fit yet" in text


def test_watchlist_filters(client, db):
    login(client)
    _add(client)
    _add(client, destination="KUL")
    page = client.get("/watchlist").text
    assert "MUC→SIN" in page and "MUC→KUL" in page and 'name="origin"' in page
    only = client.get("/watchlist?destination=SIN").text
    assert "MUC→SIN" in only and "MUC→KUL" not in only
    assert "Nothing matches" in client.get("/watchlist?origin=FRA").text
    assert "MUC→SIN" in client.get("/watchlist?origin=Europe&destination=Asia&sort=total").text
    assert "58,000" not in client.get("/watchlist?cabin=economy").text  # business flight only
    assert client.get("/watchlist?sort=bogus&pax=99").status_code == 200


def test_watchlist_rejects_bad_items(client, db):
    login(client)
    for bad in (
        {"origin": "MU"},
        {"destination": "MUC"},
        {"date_from": "nope"},
        {"date_from": "2026-12-31", "date_to": "2026-12-01"},
        {"date_from": "2020-01-01", "date_to": "2020-01-02"},
    ):
        assert _add(client, **bad).status_code == 422
    assert Store(db, readonly=True).watch_items() == []
    _add(client)
    assert _add(client).status_code == 422  # a duplicate


def test_watchlist_requires_login(client):
    for method, path in (
        ("get", "/watchlist/1"),
        ("post", "/watchlist"),
        ("post", "/watchlist/1/delete"),
    ):
        r = getattr(client, method)(path, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"].startswith("/login")

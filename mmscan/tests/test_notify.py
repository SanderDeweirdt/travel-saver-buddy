import json
from datetime import UTC, datetime

import httpx
import pytest
from typer.testing import CliRunner

from mmscan.cli import app
from mmscan.notify import NotifyError, build_message, notify_run, select_alerts, send_slack
from mmscan.report import DISCLAIMER
from mmscan.scoring import DEAL, SKIP, WORTH
from mmscan.store import Store
from tests.helpers import config, scored, seed_current

NOW = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)
URL = "https://hooks.slack.test/services/T000/B000/SECRET"


def row(change, verdict=DEAL, **kw):
    s = scored(kw.pop("total", 700.0), **kw)
    s.updated_at = datetime.now(UTC).isoformat()
    s.verdict, s.change = verdict, change
    return s


def test_select_only_new_or_cheaper_deals(default_config_dict):
    cfg = config(default_config_dict)
    rows = [
        row("New", id="a"),
        row("Cheaper", id="b"),
        row("", id="c"),
        row("New", WORTH, id="d"),
        row("New", SKIP, id="e"),
        row("New", estimated=True, id="f"),
    ]
    assert [s.availability_id for s in select_alerts(rows, cfg)] == ["a", "b"]
    cfg = config(default_config_dict, notify={"verdicts": ["Deal", "Worth a look"]})
    assert [s.availability_id for s in select_alerts(rows, cfg)] == ["a", "b", "d"]


def test_message_lists_alerts_and_disclaimer(default_config_dict):
    cfg = config(default_config_dict, notify={"max_items": 2})
    alerts = [row("New", id=str(i), total=600.0 + i) for i in range(3)]
    alerts[0].booking_link = "https://book.test/x"
    msg = build_message(alerts, 7, cfg, NOW)
    assert msg["text"] == "mmscan: 3 new or cheaper awards"
    sections = [b for b in msg["blocks"] if b["type"] == "section"]
    assert len(sections) == 2
    assert "MUC→SIN" in sections[0]["text"]["text"]
    assert "60,000 mi + €50 fees = *€600*" in sections[0]["text"]["text"]
    assert "<https://book.test/x|Book>" in sections[0]["text"]["text"]
    footer = msg["blocks"][-1]["elements"][0]["text"]
    assert "1 more in the report" in footer and DISCLAIMER in footer


def test_send_slack_posts_json():
    seen = {}

    def handler(req):
        seen["url"] = str(req.url)
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, text="ok")

    send_slack(URL, {"text": "hi"}, httpx.MockTransport(handler))
    assert seen == {"url": URL, "body": {"text": "hi"}}


def test_send_slack_error_hides_url():
    def handler(req):
        raise httpx.ConnectError("boom " + URL, request=req)

    with pytest.raises(NotifyError) as e:
        send_slack(URL, {"text": "hi"}, httpx.MockTransport(handler))
    assert "SECRET" not in str(e.value)


def test_send_slack_non_200_raises():
    with pytest.raises(NotifyError, match="404"):
        send_slack(URL, {}, httpx.MockTransport(lambda r: httpx.Response(404, text="no_service")))


def _store_with_results(tmp_path, rows):
    store = Store(tmp_path / "db.sqlite")
    return store, seed_current(store, rows, now=NOW)


def test_nothing_to_post_sends_nothing(tmp_path, default_config_dict):
    store, run = _store_with_results(tmp_path, [row("", id="a")])
    sent = []
    n, payload = notify_run(
        store,
        config(default_config_dict),
        run,
        NOW,
        URL,
        httpx.MockTransport(lambda r: sent.append(1)),
    )
    assert (n, payload, sent) == (0, None, [])


def test_notify_run_posts_once(tmp_path, default_config_dict):
    store, run = _store_with_results(
        tmp_path, [row("New", id="a"), row("Cheaper", id="b", date="2026-12-11")]
    )
    sent = []

    def handler(req):
        sent.append(json.loads(req.content))
        return httpx.Response(200, text="ok")

    n, _ = notify_run(
        store, config(default_config_dict), run, NOW, URL, httpx.MockTransport(handler)
    )
    assert n == 2 and len(sent) == 1


def test_cli_notify_dry_run_prints_without_sending(tmp_path, monkeypatch, default_config_dict):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    (tmp_path / "data").mkdir()
    store, _ = _store_with_results(tmp_path / "data", [row("New", id="a")])
    store.close()
    (tmp_path / "data" / "db.sqlite").rename(tmp_path / "data" / "mmscan.db")
    (tmp_path / "config.yaml").write_text(json.dumps(default_config_dict))
    result = CliRunner().invoke(app, ["notify", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "Would post 1 alerts to Slack" in result.output


def test_cli_notify_without_webhook_fails_cleanly(tmp_path, monkeypatch, default_config_dict):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    (tmp_path / "data").mkdir()
    store, _ = _store_with_results(tmp_path / "data", [row("New", id="a")])
    store.close()
    (tmp_path / "data" / "db.sqlite").rename(tmp_path / "data" / "mmscan.db")
    (tmp_path / "config.yaml").write_text(json.dumps(default_config_dict))
    result = CliRunner().invoke(app, ["notify"])
    assert result.exit_code == 1
    assert "SLACK_WEBHOOK_URL is not set" in result.output


def test_stale_results_are_never_alerted(default_config_dict):
    cfg = config(default_config_dict)
    fresh, old = row("New", id="a"), row("New", id="b")
    old.updated_at = "2026-10-01T08:00:00Z"
    now = datetime.now(UTC)
    assert [s.availability_id for s in select_alerts([fresh, old], cfg, now)] == ["a"]
    assert len(select_alerts([fresh, old], cfg)) == 2  # no clock, no age rule


def test_dynamic_prices_alert_only_when_switched_on(default_config_dict):
    rows = [row("New", id="a", carriers="SQ"), row("New", id="b", carriers="LH")]
    off = config(default_config_dict)
    assert [s.availability_id for s in select_alerts(rows, off)] == ["a"]
    on = config(default_config_dict, notify={"unverified": True})
    assert [s.availability_id for s in select_alerts(rows, on)] == ["a", "b"]


def _history_then_current(tmp_path, current):
    """Fifteen economy MUC-SIN flights per carrier group at 1000 EUR already on offer, then
    `current` (what the run just changed)."""
    from datetime import timedelta

    store = Store(tmp_path / "deals.sqlite")
    past = []
    for month, carriers in (("01", "SQ"), ("03", "LH")):  # separate usual prices; dates differ
        for i in range(15):
            s = scored(
                1000.0,
                date=f"2027-{month}-{i + 1:02d}",
                cabin="economy",
                id=f"h{carriers}{i}",
                carriers=carriers,
            )
            s.updated_at = (NOW - timedelta(days=1)).isoformat()
            past.append(s)
    return store, seed_current(store, past + current, now=NOW)


def _new(total, id, **kw):
    s = scored(
        total, date=kw.pop("date", "2027-02-01"), cabin=kw.pop("cabin", "economy"), id=id, **kw
    )
    s.updated_at = NOW.isoformat()
    s.change = "New"
    return s


def test_new_deal_alert_needs_new_economy_flight_10_percent_below_usual(
    tmp_path, default_config_dict
):
    from mmscan.notify import select_new_deals
    from mmscan.offers import load_current

    current = [
        _new(800.0, "big"),  # about 20% below usual: alert
        _new(950.0, "small", date="2027-02-02"),  # 5% below: no
        _new(700.0, "biz", date="2027-02-03", cabin="business"),  # wrong cabin: no
        _new(800.0, "seen", date="2027-02-04"),
        _new(800.0, "dyn", date="2027-02-05", carriers="LH"),  # dynamic: alert, unverified
    ]
    current[3].change = ""  # seen before
    store, run = _history_then_current(tmp_path, current)
    cfg = config(default_config_dict, notify={"new_deals": {"enabled": True}})
    deals = select_new_deals(load_current(store), cfg, NOW)
    assert sorted(d.s.availability_id for d in deals) == ["big", "dyn"]
    assert next(d for d in deals if d.s.availability_id == "dyn").verified is False
    off = config(default_config_dict, notify={"new_deals": {"enabled": True, "unverified": False}})
    only_chart = select_new_deals(load_current(store), off, NOW)
    assert [d.s.availability_id for d in only_chart] == ["big"]


def test_new_deal_message_has_usual_price_and_a_link_to_check(tmp_path, default_config_dict):
    tpl = "https://mm.test/?o={origin}&d={destination}&t={date}&c={cabin_code}&n={adults}"
    store, run = _history_then_current(tmp_path, [_new(800.0, "big")])
    cfg = config(
        default_config_dict,
        notify={"new_deals": {"enabled": True}},
        miles_and_more={"link_template": tpl},
    )
    sent = []

    def handler(req):
        sent.append(json.loads(req.content))
        return httpx.Response(200, text="ok")

    n, _ = notify_run(store, cfg, run, NOW, URL, httpx.MockTransport(handler))
    assert n == 1 and len(sent) == 1
    text = sent[0]["blocks"][1]["text"]["text"]
    assert "New deal" in text and "MUC→SIN" in text and "2027-02-01" in text
    assert "vs usual €" in text and "chart price" in text
    assert "<https://mm.test/?o=MUC&d=SIN&t=2027-02-01&c=E&n=1|Check on Miles & More>" in text
    assert sent[0]["text"] == "mmscan: 1 new deal"
    # Run again with the same results: they are no longer New in a later run, so nothing posts.


def test_new_deal_alert_off_posts_nothing(tmp_path, default_config_dict):
    store, run = _history_then_current(tmp_path, [_new(800.0, "big")])
    n, payload = notify_run(store, config(default_config_dict), run, NOW, URL, None)
    assert (n, payload) == (0, None)


def test_webhook_value_is_cleaned_and_checked(monkeypatch, tmp_path):
    from mmscan.notify import WEBHOOK_ENV, webhook_from_env

    good = "https://hooks.slack.test/services/T0/B0/XYZ"
    for pasted in (good, f'"{good}"', f" '{good}' "):
        monkeypatch.setenv(WEBHOOK_ENV, pasted)
        assert webhook_from_env(tmp_path / ".env") == good
    monkeypatch.setenv(WEBHOOK_ENV, "hooks.slack.test/services/T0/B0/SECRET")
    with pytest.raises(NotifyError, match="must start with https://") as e:
        webhook_from_env(tmp_path / ".env")
    assert "SECRET" not in str(e.value)  # the secret never lands in the run log

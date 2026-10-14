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
from tests.helpers import config, scored

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
    from dataclasses import astuple

    from mmscan.scoring import SCORED_COLUMNS

    store = Store(tmp_path / "db.sqlite")
    run = store.start_run("scan", "{}", now=NOW)
    ph = ",".join("?" * (len(SCORED_COLUMNS) + 1))
    store.conn.executemany(
        f"INSERT INTO results(run_id, {', '.join(SCORED_COLUMNS)}) VALUES ({ph})",
        [(run, *astuple(s)) for s in rows],
    )
    store.conn.commit()
    return store, run


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
    store, run = _store_with_results(tmp_path, [row("New", id="a"), row("Cheaper", id="b")])
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

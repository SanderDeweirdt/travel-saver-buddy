"""Slack alerts: post new or cheaper shortlist results to an incoming webhook."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv

from mmscan.config import Config
from mmscan.models import local_time
from mmscan.report import DISCLAIMER, eligible, load_results
from mmscan.scoring import SKIP, Scored, rank_key
from mmscan.store import Store

WEBHOOK_ENV = "SLACK_WEBHOOK_URL"
log = logging.getLogger("mmscan.notify")


class NotifyError(Exception):
    pass


def webhook_from_env(dotenv_path: Path | None = None) -> str:
    load_dotenv(dotenv_path or Path(".env"))
    url = os.environ.get(WEBHOOK_ENV, "").strip()
    if not url:
        raise NotifyError(
            f"{WEBHOOK_ENV} is not set. Put the Slack incoming webhook URL in .env "
            f"(see .env.example)."
        )
    return url


def select_alerts(results: list[Scored], cfg: Config) -> list[Scored]:
    """Shortlist rows whose verdict is in notify.verdicts and whose change is in notify.changes,
    plus (notify.on_drop) any eligible result that got cheaper, whatever its verdict."""
    n = cfg.notify
    out = [
        s
        for s in eligible(results, cfg)
        if (s.verdict in n.verdicts and s.change in n.changes)
        or (n.on_drop and s.change == "Cheaper")
    ]
    return sorted(out, key=rank_key)


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _line(s: Scored) -> str:
    label = s.change if s.verdict == SKIP else f"{s.change} {s.verdict}"
    seats = s.seats if s.seats is not None else "unknown"
    stops = "direct" if s.stops == 0 else f"{s.stops} stop{'s' if s.stops != 1 else ''}"
    route = f"{s.origin}→{s.destination}"
    parts = [
        f"*{_esc(label)}* · {route} · {s.date} · {s.cabin}",
        f"{s.miles:,} mi + €{s.fees_eur:.0f} fees = *€{s.total_eur:.0f}*",
        f"{stops}, seats {seats}",
    ]
    if s.flight_numbers:
        parts.append(_esc(s.flight_numbers))
    if s.departs_at:
        parts.append(f"dep {local_time(s.departs_at)}")
    if s.saving_eur is not None:
        parts.append(f"saves €{s.saving_eur:.0f} vs cash")
    line = " · ".join(parts[:2]) + "\n" + " · ".join(parts[2:])
    if s.booking_link:
        line += f"\n<{s.booking_link}|Book>"
    return line


def build_message(alerts: list[Scored], run_id: int, cfg: Config, now: datetime) -> dict:
    shown = alerts[: cfg.notify.max_items]
    title = f"mmscan: {len(alerts)} new or cheaper award{'s' if len(alerts) != 1 else ''}"
    blocks: list[dict] = [{"type": "header", "text": {"type": "plain_text", "text": title}}]
    for s in shown:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": _line(s)}})
    more = len(alerts) - len(shown)
    footer = f"Run {run_id}, {now.strftime('%Y-%m-%d %H:%M')} UTC. "
    if more:
        footer += f"{more} more in the report. "
    footer += DISCLAIMER
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": footer}]})
    return {"text": title, "blocks": blocks}


def send_slack(url: str, payload: dict, transport: httpx.BaseTransport | None = None) -> None:
    try:
        with httpx.Client(transport=transport, timeout=15.0) as http:
            resp = http.post(url, json=payload)
    except httpx.HTTPError as e:
        # The URL is a secret: name the error type only.
        raise NotifyError(f"Slack webhook request failed: {type(e).__name__}") from e
    if resp.status_code != 200:
        raise NotifyError(f"Slack webhook returned {resp.status_code}: {resp.text[:200]}")


def notify_run(
    store: Store,
    cfg: Config,
    run_id: int,
    now: datetime,
    url: str | None,
    transport: httpx.BaseTransport | None = None,
) -> tuple[int, dict | None]:
    """Post the run's alerts. Returns (alert count, payload). Sends nothing when there are no
    alerts, or when `url` is None (dry run)."""
    alerts = select_alerts(load_results(store, run_id), cfg)
    if not alerts:
        return 0, None
    payload = build_message(alerts, run_id, cfg, now)
    if url is not None:
        send_slack(url, payload, transport)
        log.info("posted %d alerts to Slack", len(alerts))
    return len(alerts), payload

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
from mmscan.report import DISCLAIMER, _age_hours, eligible, load_results
from mmscan.scoring import SKIP, Scored, rank_key
from mmscan.store import Store
from mmscan.trips import STALE_HOURS, TripAlert, trip_alerts

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


def select_alerts(results: list[Scored], cfg: Config, now: datetime | None = None) -> list[Scored]:
    """Shortlist rows whose verdict is in notify.verdicts and whose change is in notify.changes,
    plus (notify.on_drop) any eligible result that got cheaper, whatever its verdict. With `now`,
    results older than 48 hours are left out. Dynamic-carrier prices are left out too, unless
    notify.unverified is on."""
    n = cfg.notify
    out = [
        s
        for s in eligible(results, cfg)
        if (s.verdict in n.verdicts and s.change in n.changes)
        or (n.on_drop and s.change == "Cheaper")
    ]
    if now is not None:
        out = [s for s in out if not _stale(s, now)]
    if not n.unverified:
        out = [s for s in out if cfg.pricing_model(s.carriers) == "fixed"]
    return sorted(out, key=rank_key)


def _stale(s: Scored, now: datetime) -> bool:
    age = _age_hours(s.updated_at, now)
    return age is not None and age > STALE_HOURS


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


def _trip_line(a: TripAlert) -> str:
    p = a.pair
    label = a.change + (f" (was €{a.was:,.0f})" if a.was is not None else "")
    head = f"*{_esc(label)}* · {_esc(p.trip)} · {p.cabin}"
    legs = [f"Out {p.out.date} {p.out.origin}→{p.out.destination}"]
    if p.back:
        legs.append(f"Back {p.back.date} {p.back.origin}→{p.back.destination}")
        legs.append(f"{p.stay_days} days")
    money = (
        f"{p.seats} travellers: {p.miles_pp * p.seats:,} mi + €{p.fees_pp * p.seats:,.0f} fees = "
        f"*€{p.party_total:,.0f}* (€{p.total_pp:,.0f} each)"
    )
    if p.within_budget:
        money += " · within budget"
    line = f"{head}\n{' · '.join(legs)}\n{money}"
    links = [
        f"<{s.booking_link}|Book {w}>"
        for w, s in zip(("out", "back"), p.legs, strict=False)
        if s.booking_link
    ]
    return line + ("\n" + " · ".join(links) if links else "")


def build_message(
    alerts: list[Scored],
    run_id: int,
    cfg: Config,
    now: datetime,
    trips: list[TripAlert] | None = None,
) -> dict:
    trips = trips or []
    total = len(alerts) + len(trips)
    title = f"mmscan: {total} new or cheaper award{'s' if total != 1 else ''}"
    blocks: list[dict] = [{"type": "header", "text": {"type": "plain_text", "text": title}}]
    room = cfg.notify.max_items
    shown_trips = trips[:room]
    for a in shown_trips:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": _trip_line(a)}})
    shown = alerts[: max(room - len(shown_trips), 0)]
    for s in shown:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": _line(s)}})
    more = total - len(shown) - len(shown_trips)
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
    alerts = select_alerts(load_results(store, run_id), cfg, now)
    trips = trip_alerts(store, cfg, run_id, now)
    if not alerts and not trips:
        return 0, None
    payload = build_message(alerts, run_id, cfg, now, trips)
    n = len(alerts) + len(trips)
    if url is not None:
        send_slack(url, payload, transport)
        log.info("posted %d alerts to Slack", n)
    return n, payload

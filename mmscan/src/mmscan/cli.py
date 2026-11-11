"""Command-line entry point."""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated

import typer

from mmscan.client import ApiError, Client
from mmscan.config import Config, ConfigError, load_config
from mmscan.db import is_postgres_url
from mmscan.store import FULL_RUNS, Store, read_overrides

DB_PATH = Path("data/mmscan.db")
LIVE_FIXTURES = Path("tests/fixtures/live")

app = typer.Typer(help="Miles & More award scanner (seats.aero).", no_args_is_help=True)


def database_target() -> Path | str:
    """DATABASE_URL (Postgres) when set, else the local SQLite file."""
    return os.environ.get("DATABASE_URL") or DB_PATH


def _store() -> Store:
    return Store(database_target())


def _watch_items() -> list[dict]:
    """The Watchlist page's items, for planning calls; none when there is no database yet."""
    target = database_target()
    if not is_postgres_url(target) and not Path(target).exists():
        return []
    store = Store(target, readonly=True)
    try:
        return store.watch_items()
    finally:
        store.close()


ConfigOpt = Annotated[Path, typer.Option("--config", help="Path to config.yaml.")]
DryRunOpt = Annotated[bool, typer.Option("--dry-run", help="Print requests, send nothing.")]
VerboseOpt = Annotated[bool, typer.Option("--verbose", "-v", help="Debug logging.")]


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        # stdout, not the stderr default: hosts like Railway tag all stderr
        # output as severity=error, even for INFO lines.
        stream=sys.stdout,
    )
    if not verbose:
        # One INFO line per paginated API request is too noisy.
        logging.getLogger("httpx").setLevel(logging.WARNING)


def _load(config: Path) -> Config:
    try:
        cfg = load_config(config, read_overrides(database_target()))
    except ConfigError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(2) from e
    for w in cfg.warnings:
        typer.echo(f"warning: {w}", err=True)
    return cfg


@app.command()
def check(
    config: ConfigOpt = Path("config.yaml"),
    dry_run: DryRunOpt = False,
    verbose: VerboseOpt = False,
) -> None:
    """Four small calls to confirm the key works; saves raw JSON fixtures."""
    from mmscan.check import describe, planned_check_requests, run_check

    _setup_logging(verbose)
    if dry_run:
        typer.echo("Would send 4 requests:")
        for path, params in planned_check_requests():
            typer.echo(f"  GET /{path} {params}")
        return
    cap = _load(config).api.daily_call_cap if config.exists() else 300
    store = _store()
    store.purge_older_than(180)
    run_id = store.start_run("check", "{}")
    try:
        client = Client.from_env(store, run_id, cap)
        paths = run_check(client, LIVE_FIXTURES, client.api_key)
    except ApiError as e:
        store.finish_run(run_id, "failed", {}, [str(e)])
        typer.echo(f"check failed: {e}", err=True)
        raise typer.Exit(1) from e
    store.finish_run(run_id, "ok", {"calls": client.calls_made}, [])
    typer.echo(describe(paths))
    typer.echo(f"Saved {len(paths)} fixtures to {LIVE_FIXTURES}/ ({client.calls_made} calls).")


@app.command()
def scan(
    config: ConfigOpt = Path("config.yaml"),
    dry_run: DryRunOpt = False,
    verbose: VerboseOpt = False,
) -> None:
    """Steps 1 and 2: scan regions and the watchlist."""
    from mmscan.scan import planned_requests, run_scan

    _setup_logging(verbose)
    cfg = _load(config)
    today = date.today()
    if dry_run:
        reqs = planned_requests(cfg, today, _watch_items())
        typer.echo(f"Would start with {len(reqs)} requests (more pages as results require):")
        for path, params in reqs:
            typer.echo(f"  GET /{path} {params}")
        return
    store = _store()
    store.purge_older_than(180)
    run_id = store.start_run("scan", cfg.model_dump_json())
    try:
        client = Client.from_env(store, run_id, cfg.api.daily_call_cap)
    except ApiError as e:
        store.finish_run(run_id, "failed", {}, [str(e)])
        typer.echo(f"scan failed: {e}", err=True)
        raise typer.Exit(1) from e
    status, stats = run_scan(client, store, cfg, run_id, today)
    for w in stats["warnings"]:
        typer.echo(f"warning: {w}", err=True)
    typer.echo(
        f"Scan {status}: {stats['region_results']} region results, "
        f"{stats['watchlist_results']} watchlist results with {stats['watchlist_trips']} trips, "
        f"{stats['calls']} API calls."
    )
    if status != "ok":
        raise typer.Exit(1)


def _fares(config: Path):
    from mmscan.fares import CsvFareSource

    return CsvFareSource(config.parent / "cash_fares.csv")


def _client(store: Store, run_id: int, cfg: Config) -> Client:
    try:
        return Client.from_env(store, run_id, cfg.api.daily_call_cap)
    except ApiError as e:
        store.merge_run(run_id, "failed", warnings=[str(e)])
        typer.echo(f"failed: {e}", err=True)
        raise typer.Exit(1) from e


def _scanned_run(store: Store) -> int:
    run_id = store.latest_scanned_run(FULL_RUNS)
    if run_id is None:
        typer.echo("No scan stored yet. Run `mmscan scan` first.", err=True)
        raise typer.Exit(1)
    return run_id


def _do_enrich(
    client: Client, store: Store, cfg: Config, run_id: int, candidates: list[str]
) -> bool:
    """Fetch trips for the candidates. Returns False when the daily cap stopped it."""
    from mmscan.enrich import enrich as run_enrich
    from mmscan.enrich import fee_spread

    stats = run_enrich(client, store, cfg, run_id, candidates)
    store.merge_run(
        run_id,
        "partial" if stats.cap_reached else None,
        {
            "candidates": len(candidates),
            "trips_called": stats.called,
            "priced": stats.priced,
            "expired": stats.expired,
            "skipped_cached": stats.skipped_cached,
            "left_over": stats.left_over,
            "calls": store.conn.execute(
                "SELECT count(*) FROM api_calls WHERE run_id=?", (run_id,)
            ).fetchone()[0],
        },
        ["Daily call cap reached during enrich"] if stats.cap_reached else [],
    )
    typer.echo(
        f"Enrich: {len(candidates)} candidates, {stats.called} Get Trips calls, "
        f"{stats.priced} priced, {stats.expired} expired, {stats.skipped_cached} already cached, "
        f"{stats.left_over} left for the next run."
    )
    spread = fee_spread(store, cfg.usd_to_eur)
    if spread:
        typer.echo("Fee spread per route and cabin (EUR): n, min, median, max")
        for o, d, c, n, lo, med, hi in spread:
            typer.echo(f"  {o}-{d} {c}: {n}, {lo:.2f}, {med:.2f}, {hi:.2f}")
    return not stats.cap_reached


def _do_score(store: Store, cfg: Config, run_id: int, config: Path) -> None:
    from mmscan.scoring import score_run

    scored, warnings = score_run(store, cfg, run_id, datetime.now(UTC), _fares(config))
    store.merge_run(run_id, stats={"scored": len(scored)}, warnings=warnings)
    for w in warnings:
        typer.echo(f"warning: {w}", err=True)
    typer.echo(f"Scored {len(scored)} current offers after run {run_id}.")


def _do_report(store: Store, cfg: Config, run_id: int) -> None:
    from mmscan.report import print_summary, write_report

    now = datetime.now(UTC)
    if report_dir := os.environ.get("MMSCAN_REPORT_DIR"):
        cfg.output.dir = Path(report_dir)  # cron runs keep no reports on disk
    for p in write_report(store, cfg, run_id, now):
        typer.echo(f"Wrote {p}")
    print_summary(store, run_id, cfg, now)


def _do_notify(store: Store, cfg: Config, run_id: int, dry_run: bool = False) -> bool:
    """Post Slack alerts for the run. Returns False when sending failed."""
    import json

    from mmscan.notify import NotifyError, notify_run, webhook_from_env

    try:
        url = None if dry_run else webhook_from_env()
        n, payload = notify_run(store, cfg, run_id, datetime.now(UTC), url)
    except NotifyError as e:
        store.merge_run(run_id, warnings=[str(e)])
        typer.echo(f"notify failed: {e}", err=True)
        return False
    if n == 0:
        typer.echo("Slack: no new or cheaper results to post.")
    elif dry_run:
        typer.echo(f"Would post {n} alerts to Slack:")
        typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        typer.echo(f"Slack: posted {n} alerts.")
    return True


@app.command()
def enrich(
    config: ConfigOpt = Path("config.yaml"),
    dry_run: DryRunOpt = False,
    verbose: VerboseOpt = False,
) -> None:
    """Steps 3 and 4: pre-screen and fetch trips (fees) for candidates."""
    from mmscan.enrich import select_candidates

    _setup_logging(verbose)
    cfg = _load(config)
    if dry_run and not DB_PATH.exists():
        typer.echo("No scan stored yet; nothing to enrich.")
        return
    store = _store()
    run_id = _scanned_run(store)
    if dry_run:
        candidates = select_candidates(store, cfg, run_id)
        n = min(len(candidates), cfg.enrich.max_calls)
        typer.echo(f"Run {run_id}: {len(candidates)} candidates; would make {n} Get Trips calls.")
        for avail_id in candidates[:n][:10]:
            typer.echo(f"  GET /trips/{avail_id}")
        return
    client = _client(store, run_id, cfg)
    if not _do_enrich(client, store, cfg, run_id, select_candidates(store, cfg, run_id)):
        raise typer.Exit(1)


@app.command()
def score(
    config: ConfigOpt = Path("config.yaml"),
    dry_run: DryRunOpt = False,
    verbose: VerboseOpt = False,
) -> None:
    """Step 5: score every result. No API calls."""
    _setup_logging(verbose)
    cfg = _load(config)
    if dry_run:
        typer.echo("Would score the latest scanned run. 0 API calls.")
        return
    store = _store()
    _do_score(store, cfg, _scanned_run(store), config)


@app.command()
def report(
    config: ConfigOpt = Path("config.yaml"),
    dry_run: DryRunOpt = False,
    verbose: VerboseOpt = False,
) -> None:
    """Step 6: write the spreadsheet and CSV. No API calls."""
    _setup_logging(verbose)
    cfg = _load(config)
    if dry_run:
        typer.echo(f"Would write the report for the latest scored run to {cfg.output.dir}.")
        return
    store = _store()
    run_id = store.latest_scanned_run(FULL_RUNS)
    if run_id is None:
        typer.echo("No scored run yet. Run `mmscan score` first.", err=True)
        raise typer.Exit(1)
    _do_report(store, cfg, run_id)


def _check_storage(store: Store, cfg: Config) -> None:
    """Warn on stderr, and in Slack when it is on, if the database is filling the volume."""
    from mmscan.notify import (
        NotifyError,
        send_slack,
        storage_usage,
        storage_warning,
        webhook_from_env,
    )

    try:
        usage = storage_usage(store.size_report(), cfg)
    except Exception as e:  # a size check must never fail the scan
        typer.echo(f"storage check failed: {type(e).__name__}", err=True)
        return
    typer.echo(f"Database: {usage['used_bytes'] / 1024**2:.0f} MB, {usage['pct']}% of the volume.")
    text = storage_warning(usage, cfg)
    if not text:
        return
    typer.echo(text, err=True)
    if cfg.notify.slack:
        try:
            send_slack(webhook_from_env(), {"text": text})
        except NotifyError as e:
            typer.echo(f"storage alert failed: {e}", err=True)


def _run_config_json(cfg: Config) -> str:
    """The run's stored config, tagged with the Railway deployment so `deploy-pending` can tell
    that this deployment has scanned."""
    data = json.loads(cfg.model_dump_json())
    if deployment := os.environ.get("RAILWAY_DEPLOYMENT_ID"):
        data["deployment_id"] = deployment
    return json.dumps(data)


@app.command("deploy-pending")
def deploy_pending() -> None:
    """Exit 0 when this Railway deployment has not run a full scan yet, 1 otherwise (or when not
    on Railway). cron.sh uses it to scan on the first tick after every deployment."""
    deployment = os.environ.get("RAILWAY_DEPLOYMENT_ID")
    if not deployment or _store().deployment_scanned(deployment):
        raise typer.Exit(1)
    typer.echo(f"Deployment {deployment} has not scanned yet.")


@app.command()
def vacuum(
    table: Annotated[
        list[str] | None, typer.Option("--table", help="Only this table (repeatable).")
    ] = None,
    verbose: VerboseOpt = False,
) -> None:
    """Give disk space freed by the purge back to the volume (Postgres VACUUM FULL, one table at
    a time, each locked while it runs). Run it between scans; cron.sh does so monthly."""
    _setup_logging(verbose)
    store = _store()
    before = store.size_report()["total_bytes"]
    done = store.vacuum(table or ())
    after = store.size_report()["total_bytes"]
    typer.echo(
        f"Vacuumed {len(done)} table(s): {before / 1024**2:.0f} MB -> {after / 1024**2:.0f} MB."
    )


def _slack_test(dry_run: bool) -> None:
    """Send a hello world through the same webhook loading and sending the alerts use."""
    from mmscan.notify import NotifyError, send_slack, webhook_from_env

    payload = {"text": "Hello world from mmscan :wave: (webhook test, safe to ignore)"}
    try:
        url = webhook_from_env()
        if dry_run:
            typer.echo(f"Would post {payload['text']!r} to the webhook ({len(url)} characters).")
            return
        send_slack(url, payload)
    except NotifyError as e:
        typer.echo(f"Slack test failed: {e}", err=True)
        raise typer.Exit(1) from e
    typer.echo("Slack test posted: check the channel the webhook belongs to.")


@app.command()
def notify(
    config: ConfigOpt = Path("config.yaml"),
    dry_run: DryRunOpt = False,
    verbose: VerboseOpt = False,
    test: Annotated[
        bool,
        typer.Option("--test", help="Post a 'Hello world' to check the webhook; reads no data."),
    ] = False,
) -> None:
    """Post new or cheaper results of the latest scored run to Slack. No API calls."""
    _setup_logging(verbose)
    if test:
        _slack_test(dry_run)
        return
    cfg = _load(config)
    target = database_target()
    if isinstance(target, Path) and not target.exists():
        typer.echo("No scored run yet. Run `mmscan score` first.", err=True)
        raise typer.Exit(1)
    store = _store()
    run_id = store.latest_scanned_run()
    if run_id is None:
        typer.echo("No scored run yet. Run `mmscan score` first.", err=True)
        raise typer.Exit(1)
    if not _do_notify(store, cfg, run_id, dry_run):
        raise typer.Exit(1)


@app.command()
def run(
    config: ConfigOpt = Path("config.yaml"),
    dry_run: DryRunOpt = False,
    verbose: VerboseOpt = False,
) -> None:
    """All steps in order."""
    from mmscan.scan import planned_requests, run_scan

    _setup_logging(verbose)
    cfg = _load(config)
    today = date.today()
    reqs = planned_requests(cfg, today, _watch_items())
    typer.echo(
        f"Planned calls: {len(reqs)} scan requests plus extra pages as results require, "
        f"then up to {cfg.enrich.max_calls} Get Trips calls for Shortlist results. "
        f"Score and report make none."
    )
    if dry_run:
        for path, params in reqs:
            typer.echo(f"  GET /{path} {params}")
        return
    store = _store()
    store.purge_older_than(180)
    run_id = store.start_run("run", _run_config_json(cfg))
    client = _client(store, run_id, cfg)
    status, stats = run_scan(client, store, cfg, run_id, today)
    for w in stats["warnings"]:
        typer.echo(f"warning: {w}", err=True)
    typer.echo(
        f"Scan {status}: {stats['region_results']} region results, "
        f"{stats['watchlist_results']} watchlist results, {stats['calls']} API calls."
    )
    if status == "failed":
        raise typer.Exit(1)
    # Fees come with the scan (summary taxes). Score first, then fetch trip details (flight
    # numbers, times, booking link) only for results that made the Shortlist, and score again.
    _do_score(store, cfg, run_id, config)
    complete = status == "ok"
    if complete:
        from mmscan.enrich import shortlist_candidates

        candidates = shortlist_candidates(store, cfg, run_id)
        if candidates and cfg.enrich.max_calls:
            complete = _do_enrich(client, store, cfg, run_id, candidates)
            _do_score(store, cfg, run_id, config)
    _do_report(store, cfg, run_id)
    if cfg.notify.slack:
        _do_notify(store, cfg, run_id)
    _check_storage(store, cfg)
    if not complete:
        typer.echo("Run is partial: the daily call cap stopped it early.", err=True)
        raise typer.Exit(1)


@app.command()
def watch(
    config: ConfigOpt = Path("config.yaml"),
    dry_run: DryRunOpt = False,
    verbose: VerboseOpt = False,
) -> None:
    """Watchlist only: scan, score against stored history and post new deals to Slack.
    Made for frequent runs (cron, hourly); costs 2 x watch.max_pages calls."""
    from mmscan.scan import run_scan, watchlist_requests

    _setup_logging(verbose)
    cfg = _load(config)
    today = date.today()
    reqs = watchlist_requests(cfg, today, _watch_items())
    if not reqs:
        typer.echo("The watchlist is empty; nothing to watch.", err=True)
        raise typer.Exit(1)
    typer.echo(f"Planned calls: at most {len(reqs) * cfg.watch.max_pages}. Scoring makes none.")
    if dry_run:
        for path, params in reqs:
            typer.echo(f"  GET /{path} { ({**params, 'take': cfg.api.take}) }")
        return
    store = _store()
    store.purge_older_than(180)
    run_id = store.start_run("watch", cfg.model_dump_json())
    client = _client(store, run_id, cfg)
    status, stats = run_scan(client, store, cfg, run_id, today, watch_only=True)
    for w in stats["warnings"]:
        typer.echo(f"warning: {w}", err=True)
    typer.echo(
        f"Watch {status}: {stats['watchlist_results']} results with "
        f"{stats['watchlist_trips']} trips, {stats['calls']} API calls."
    )
    if status == "failed":
        raise typer.Exit(1)
    _do_score(store, cfg, run_id, config)
    if cfg.notify.slack:
        _do_notify(store, cfg, run_id)
    else:
        from mmscan.notify import select_alerts
        from mmscan.offers import load_current

        n = len(select_alerts(load_current(store), cfg))
        typer.echo(f"{n} new or cheaper results (Slack is off: notify.slack is false).")
    if status != "ok":
        raise typer.Exit(1)


@app.command()
def trips(
    config: ConfigOpt = Path("config.yaml"),
    top: Annotated[int, typer.Option(help="Pairs to show per trip.")] = 5,
) -> None:
    """Best round trips per trip profile, from stored results. Makes no API calls."""
    from mmscan.trips import trip_views

    cfg = _load(config)
    if not cfg.trips:
        typer.echo("No trips configured; add a trips: block to config.yaml.", err=True)
        raise typer.Exit(1)
    store = _store()
    for v in trip_views(store, cfg, datetime.now(UTC)):
        typer.echo(f"\n{v.profile.name} ({v.seats} seat{'s' if v.seats != 1 else ''})")
        if not v.pairs:
            typer.echo(f"  {v.note}")
        for p in v.pairs[:top]:
            back = f" -> {p.back.date} {p.back.origin}-{p.back.destination}" if p.back else ""
            budget = {True: " [within budget]", False: " [over budget]", None: ""}[p.within_budget]
            typer.echo(
                f"  EUR {p.party_total:,.0f} ({p.total_pp:,.0f} each) {p.cabin}: "
                f"{p.out.date} {p.out.origin}-{p.out.destination}{back}{budget}"
            )


@app.command()
def quota(
    config: ConfigOpt = Path("config.yaml"),
    dry_run: DryRunOpt = False,
    verbose: VerboseOpt = False,
) -> None:
    """Calls left today and calls made by this tool. No API calls."""
    cap = _load(config).api.daily_call_cap if config.exists() else 300
    target = database_target()
    if isinstance(target, Path) and not target.exists():
        typer.echo(f"No calls recorded yet. Daily cap: {cap}.")
        return
    store = _store()
    remaining = store.last_rate_remaining()
    typer.echo(
        f"X-RateLimit-Remaining (last call): {'unknown' if remaining is None else remaining}"
    )
    typer.echo(f"Calls by mmscan today (UTC): {store.calls_today()} of cap {cap}")


@app.command("verify-add")
def verify_add(
    carrier: Annotated[str, typer.Option(help="IATA code, e.g. LH")],
    cached: Annotated[int, typer.Option(min=1, help="Miles seats.aero cached")],
    live: Annotated[int, typer.Option(min=1, help="Miles miles-and-more.com showed")],
    route: Annotated[str | None, typer.Option(help="e.g. MUC-SIN")] = None,
    cabin: Annotated[str | None, typer.Option()] = None,
    note: Annotated[str | None, typer.Option()] = None,
) -> None:
    """Record one hand check of a cached price against the live one. No API calls."""
    store = _store()
    store.add_price_check(carrier, cached, live, route, cabin, note)
    typer.echo(
        f"{carrier.upper()}: live is {live / cached:.2f}x the cached miles ({cached} -> {live})."
    )


@app.command("migrate-sqlite")
def migrate_sqlite(
    source: Annotated[Path, typer.Option("--from", help="SQLite file to copy from.")] = DB_PATH,
) -> None:
    """Copy a local SQLite database into the Postgres database in DATABASE_URL. Safe to repeat:
    rows already there are left alone."""
    from mmscan.migrate import migrate

    url = os.environ.get("DATABASE_URL")
    if not url:
        typer.echo("DATABASE_URL is not set; it names the Postgres target.", err=True)
        raise typer.Exit(2)
    if not source.exists():
        typer.echo(f"{source} does not exist.", err=True)
        raise typer.Exit(2)
    for table, copied, total in migrate(source, url):
        typer.echo(f"{table}: {copied} new rows copied, {total} in the source")


@app.command()
def web(
    host: Annotated[str, typer.Option(help="Interface to bind.")] = "0.0.0.0",
    port: Annotated[int, typer.Option(envvar="PORT", help="Port; Railway sets PORT.")] = 8000,
) -> None:
    """Private dashboard; only Settings writes. Needs DASHBOARD_PASSWORD and SESSION_SECRET."""
    import uvicorn

    from mmscan.web.app import create_app
    from mmscan.web.settings import SettingsError, settings_from_env

    try:
        application = create_app(settings_from_env())
    except SettingsError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(2) from e
    uvicorn.run(application, host=host, port=port, proxy_headers=True, forwarded_allow_ips="*")

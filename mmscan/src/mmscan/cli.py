"""Command-line entry point."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated

import typer

from mmscan.client import ApiError, Client
from mmscan.config import Config, ConfigError, load_config
from mmscan.store import Store

DB_PATH = Path("data/mmscan.db")
FULL_RUNS = ("scan", "run")  # watch runs hold only the watchlist
LIVE_FIXTURES = Path("tests/fixtures/live")

app = typer.Typer(help="Miles & More award scanner (seats.aero).", no_args_is_help=True)


ConfigOpt = Annotated[Path, typer.Option("--config", help="Path to config.yaml.")]
DryRunOpt = Annotated[bool, typer.Option("--dry-run", help="Print requests, send nothing.")]
VerboseOpt = Annotated[bool, typer.Option("--verbose", "-v", help="Debug logging.")]


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _load(config: Path) -> Config:
    try:
        cfg = load_config(config)
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
    store = Store(DB_PATH)
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
        reqs = planned_requests(cfg, today)
        typer.echo(f"Would start with {len(reqs)} requests (more pages as results require):")
        for path, params in reqs:
            typer.echo(f"  GET /{path} {params}")
        return
    store = Store(DB_PATH)
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


def _do_enrich(client: Client, store: Store, cfg: Config, run_id: int) -> bool:
    """Returns False when the daily cap stopped it."""
    from mmscan.enrich import enrich as run_enrich
    from mmscan.enrich import fee_spread, select_candidates

    candidates = select_candidates(store, cfg, run_id)
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
    spread = fee_spread(store)
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
    typer.echo(f"Scored {len(scored)} results in run {run_id}.")


def _do_report(store: Store, cfg: Config, run_id: int) -> None:
    from mmscan.report import print_summary, write_report

    now = datetime.now(UTC)
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
    store = Store(DB_PATH)
    run_id = _scanned_run(store)
    if dry_run:
        candidates = select_candidates(store, cfg, run_id)
        n = min(len(candidates), cfg.enrich.max_calls)
        typer.echo(f"Run {run_id}: {len(candidates)} candidates; would make {n} Get Trips calls.")
        for avail_id in candidates[:n][:10]:
            typer.echo(f"  GET /trips/{avail_id}")
        return
    client = _client(store, run_id, cfg)
    if not _do_enrich(client, store, cfg, run_id):
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
    store = Store(DB_PATH)
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
    store = Store(DB_PATH)
    run_id = store.latest_scored_run(FULL_RUNS)
    if run_id is None:
        typer.echo("No scored run yet. Run `mmscan score` first.", err=True)
        raise typer.Exit(1)
    _do_report(store, cfg, run_id)


@app.command()
def notify(
    config: ConfigOpt = Path("config.yaml"),
    dry_run: DryRunOpt = False,
    verbose: VerboseOpt = False,
) -> None:
    """Post new or cheaper results of the latest scored run to Slack. No API calls."""
    _setup_logging(verbose)
    cfg = _load(config)
    if not DB_PATH.exists():
        typer.echo("No scored run yet. Run `mmscan score` first.", err=True)
        raise typer.Exit(1)
    store = Store(DB_PATH)
    run_id = store.latest_scored_run()
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
    reqs = planned_requests(cfg, today)
    typer.echo(
        f"Planned calls: {len(reqs)} scan requests plus extra pages as results require, "
        f"then up to {cfg.enrich.max_calls} Get Trips calls. Score and report make none."
    )
    if dry_run:
        for path, params in reqs:
            typer.echo(f"  GET /{path} {params}")
        return
    store = Store(DB_PATH)
    store.purge_older_than(180)
    run_id = store.start_run("run", cfg.model_dump_json())
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
    complete = status == "ok" and _do_enrich(client, store, cfg, run_id)
    _do_score(store, cfg, run_id, config)
    _do_report(store, cfg, run_id)
    if cfg.notify.slack:
        _do_notify(store, cfg, run_id)
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
    reqs = watchlist_requests(cfg, today)
    if not reqs:
        typer.echo("The watchlist is empty; nothing to watch.", err=True)
        raise typer.Exit(1)
    typer.echo(f"Planned calls: at most {len(reqs) * cfg.watch.max_pages}. Scoring makes none.")
    if dry_run:
        for path, params in reqs:
            typer.echo(f"  GET /{path} { ({**params, 'take': cfg.api.take}) }")
        return
    store = Store(DB_PATH)
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
        from mmscan.report import load_results

        n = len(select_alerts(load_results(store, run_id), cfg))
        typer.echo(f"{n} new or cheaper results (Slack is off: notify.slack is false).")
    if status != "ok":
        raise typer.Exit(1)


@app.command()
def quota(
    config: ConfigOpt = Path("config.yaml"),
    dry_run: DryRunOpt = False,
    verbose: VerboseOpt = False,
) -> None:
    """Calls left today and calls made by this tool. No API calls."""
    cap = _load(config).api.daily_call_cap if config.exists() else 300
    if not DB_PATH.exists():
        typer.echo(f"No calls recorded yet. Daily cap: {cap}.")
        return
    store = Store(DB_PATH)
    remaining = store.last_rate_remaining()
    typer.echo(
        f"X-RateLimit-Remaining (last call): {'unknown' if remaining is None else remaining}"
    )
    typer.echo(f"Calls by mmscan today (UTC): {store.calls_today()} of cap {cap}")

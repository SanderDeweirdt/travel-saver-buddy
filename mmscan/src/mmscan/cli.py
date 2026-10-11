"""Command-line entry point."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

import typer

from mmscan.client import ApiError, Client
from mmscan.config import Config, ConfigError, load_config
from mmscan.store import Store

DB_PATH = Path("data/mmscan.db")
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


def _todo(name: str) -> None:
    typer.echo(f"mmscan {name}: not built yet.")
    raise typer.Exit(1)


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
    _todo("scan")


@app.command()
def enrich(
    config: ConfigOpt = Path("config.yaml"),
    dry_run: DryRunOpt = False,
    verbose: VerboseOpt = False,
) -> None:
    """Steps 3 and 4: pre-screen and fetch trips (fees) for candidates."""
    _todo("enrich")


@app.command()
def score(
    config: ConfigOpt = Path("config.yaml"),
    dry_run: DryRunOpt = False,
    verbose: VerboseOpt = False,
) -> None:
    """Step 5: score every result. No API calls."""
    _todo("score")


@app.command()
def report(
    config: ConfigOpt = Path("config.yaml"),
    dry_run: DryRunOpt = False,
    verbose: VerboseOpt = False,
) -> None:
    """Step 6: write the spreadsheet and CSV. No API calls."""
    _todo("report")


@app.command()
def run(
    config: ConfigOpt = Path("config.yaml"),
    dry_run: DryRunOpt = False,
    verbose: VerboseOpt = False,
) -> None:
    """All steps in order."""
    _todo("run")


@app.command()
def quota(
    config: ConfigOpt = Path("config.yaml"),
    dry_run: DryRunOpt = False,
    verbose: VerboseOpt = False,
) -> None:
    """Calls left today and calls made by this tool. No API calls."""
    _todo("quota")

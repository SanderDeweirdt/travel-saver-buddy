"""Command-line entry point."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

import typer

app = typer.Typer(help="Miles & More award scanner (seats.aero).", no_args_is_help=True)


ConfigOpt = Annotated[Path, typer.Option("--config", help="Path to config.yaml.")]
DryRunOpt = Annotated[bool, typer.Option("--dry-run", help="Print requests, send nothing.")]
VerboseOpt = Annotated[bool, typer.Option("--verbose", "-v", help="Debug logging.")]


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


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
    _todo("check")


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

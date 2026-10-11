# mmscan

A command-line tool that pulls Miles & More award availability from the
seats.aero API, scores every result against configurable benchmarks, and
writes a ranked shortlist. The design is in [`docs/PRD.md`](docs/PRD.md).

> Cached data. Confirm price and seats on miles-and-more.com before acting.

Personal, non-commercial use only, as the seats.aero API terms require.

## Status

All five milestones are built and tested offline (`uv run pytest`). None of
the live gates has run yet: `seats.aero` is not reachable from the build
environment, so the tests use the hand-written fixtures in
`tests/fixtures/synthetic/`. The first live step is `uv run mmscan check`;
what it finds goes in [`docs/api-findings.md`](docs/api-findings.md), and
code that relies on an API field the live response lacks gets fixed then.

## Setup

Needs Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
cd mmscan
uv sync
cp .env.example .env   # then put your seats.aero Pro API key in it
uv run mmscan check    # 4 API calls: proves the key works
```

The key is read only from `SEATS_AERO_API_KEY` (the environment or `.env`).
It never goes in `config.yaml`, logs, fixtures or reports.

## Commands

Every command takes `--config PATH` (default `config.yaml`), `--dry-run`
(print the requests, send nothing) and `--verbose`.

| Command | What it does | API calls |
| --- | --- | --- |
| `mmscan check` | Four small calls; saves the raw responses to `tests/fixtures/live/` | 4 |
| `mmscan scan` | Region pairs (Bulk Availability) and the watchlist (Cached Search, trips included) | One per page; 4 first pages with the default config |
| `mmscan enrich` | Picks the cheapest 30% of region results and fetches their trips (fees) | Up to `enrich.max_calls` (150) |
| `mmscan score` | Total cost, baselines, flags and verdicts | 0 |
| `mmscan report` | Spreadsheet, Shortlist CSV and the terminal top 10 | 0 |
| `mmscan run` | Scan, enrich, score and report in one run; prints the planned calls first | Scan plus enrich |
| `mmscan quota` | Calls left today (last `X-RateLimit-Remaining`) and calls made by mmscan today | 0 |

`enrich` and `score` work on the latest scanned run, and `report` on the
latest scored run. Get Trips results are cached per availability `ID` and
`UpdatedAt`, so a rerun does not pay for unchanged availabilities. If the
daily cap (`api.daily_call_cap`, default 300) is reached, the run stops,
keeps what it stored, is marked `partial`, and exits non-zero.

Reports go to `reports/mmscan_YYYY-MM-DD_HHMM.xlsx` (sheets Shortlist, All
results, Route stats, Run log) and `..._shortlist.csv`. The database is
`data/mmscan.db`; rows older than 180 days are deleted at the start of each
scan.

## Tuning `config.yaml`

| Block | What it changes |
| --- | --- |
| `source`, `cabins`, `min_seats` | Program, cabins read from each result, seats you need. Fewer seats are kept but flagged. |
| `mile_cost_eur_cents` | What one mile costs you; turns miles into euros for the total cost. |
| `date_window` | Days from today to scan, recalculated each run. |
| `region_pairs` | Continent-level pairs for Bulk Availability. |
| `watchlist` | Airports searched with trips included, so their fees are free. `both_directions` adds the return direction. |
| `subregions` | Airport lists that refine a continent, used by `benchmarks`. |
| `benchmarks` | Fallback ceilings per cabin and place pair, used when a baseline is thin. `chart_rate_miles` sets the chart-rate flag at 95%. |
| `relative` | `percentile_good` (deal threshold), `min_samples` (below this a baseline is unknown), `history_days` (stored runs that count). |
| `prescreen.percentile` | Share of region results, cheapest first, that get their fees fetched. |
| `enrich.max_calls` | Get Trips calls per run. Leftover candidates are picked up next run. |
| `value_per_mile_cents` | Bands for value per mile against a cash fare. |
| `api` | Page size, mixed-cabin filter, `include_filtered`, and the daily call cap. |
| `output` | Report folder and formats. |

Optional `cash_fares.csv`, next to `config.yaml`, with columns
`origin,destination,cabin,month,fare_eur` (`month` as `YYYY-MM`). Matching
results get a cash fare, saving and value per mile. Bad rows are skipped
with a warning naming the line.

## Findings

- **Live API:** pending; see [`docs/api-findings.md`](docs/api-findings.md).
- **`include_filtered` comparison (milestone 1):** pending a live scan.
- **Fee spread per route (milestone 2):** pending a live enrich.
  `mmscan enrich` prints min, median and max fee per route and cabin.

## Tests

```bash
uv run pytest -q && uv run ruff check . && uv run ruff format --check .
```

Tests never touch the network.

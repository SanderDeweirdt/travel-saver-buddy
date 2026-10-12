# mmscan

A command-line tool that pulls Miles & More award availability from the
seats.aero API, scores every result against configurable benchmarks, and
writes a ranked shortlist. The design is in [`docs/PRD.md`](docs/PRD.md).

> Cached data. Confirm price and seats on miles-and-more.com before acting.

Personal, non-commercial use only, as the seats.aero API terms require.

## Status

All five milestones are built and tested offline (`uv run pytest`). The
milestone 0 gate has run (`mmscan check`); the scan, fee-spread and
`include_filtered` gates have not. Tests use hand-written fixtures in
`tests/fixtures/synthetic/`; the recorded live responses in
`tests/fixtures/live/` are git-ignored because the seats.aero terms forbid
redistributing the data.

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
| `mmscan enrich` | By hand: picks the cheapest 30% of region results (by miles) and fetches their trip details | Up to `enrich.max_calls` (150) |
| `mmscan score` | Total cost, baselines, flags and verdicts | 0 |
| `mmscan report` | Spreadsheet, Shortlist CSV and the terminal top 10 | 0 |
| `mmscan run` | Scan, score, fetch trip details for Shortlist results only, score again, report, notify; prints the planned calls first | Scan plus at most `enrich.max_calls` |
| `mmscan watch` | Watchlist only: scan (first `watch.max_pages` page per direction), score against stored history, post new deals to Slack. For hourly runs | 2 with the default config |
| `mmscan notify` | Posts the latest run's new or cheaper Deals to Slack; nothing when there are none | 0 |
| `mmscan quota` | Calls left today (last `X-RateLimit-Remaining`) and calls made by mmscan today | 0 |

`enrich` and `score` work on the latest `scan` or `run`, and `report` on
the latest scored one; `watch` runs are left out because they hold only the
watchlist. Get Trips results are cached per availability `ID` and
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
| `usd_to_eur` | Fixed rate for fees: seats.aero reports Miles & More fees in USD. Update it now and then. Without it the Shortlist stays empty. |
| `date_window` | Days from today to scan, recalculated each run. |
| `region_pairs` | Continent-level pairs for Bulk Availability. |
| `watchlist` | Airports searched with trips included, so their fees are free. `both_directions` adds the return direction. |
| `subregions` | Airport lists that refine a continent, used by `benchmarks`. |
| `benchmarks` | Fallback ceilings per cabin and place pair, used when a baseline is thin. `chart_rate_miles` sets the chart-rate flag at 95%. |
| `relative` | `percentile_good` (deal threshold), `min_samples` (below this a baseline is unknown), `history_days` (stored runs that count), `min_discount_pct` (a route or destination only counts as good when the total is also this % below its median; 0 = plain percentile cut). Lufthansa-group fares barely move by date, so a high value leaves few Deals. |
| `deals` | `by_ceiling: true` makes a result within its benchmark's `good_miles_max` and `fees_max_eur` a Deal even when the relative baselines say no. The right way to find deals on routes whose fare never moves. Check the ceilings against real fees: the PRD's 200 EUR economy limit is below almost every real fee. |
| `drops` | `min_pct`: Change shows Cheaper when a total fell this much since it was last seen. |
| `shortlist` | `scope: focus` limits the Shortlist, the CSV and Slack to results matching a benchmark or (`focus_watchlist`) a watchlist pair; `all` keeps everything scored Deal or Worth a look. "All results" always has every result. |
| `prescreen.percentile` | Share of region results, cheapest first, that get their fees fetched. |
| `enrich.max_calls` | Get Trips calls per run: for `run` it caps trip details for Shortlist results; for `enrich` it caps the pre-screened candidates. Set to 0 to skip. |
| `value_per_mile_cents` | Bands for value per mile against a cash fare. |
| `api` | Page size, mixed-cabin filter, `include_filtered`, and the daily call cap. |
| `output` | Report folder and formats. |
| `watch.max_pages` | Pages per direction for `mmscan watch`. Results come cheapest first, so 1 page usually holds every deal. |
| `notify` | Slack alerts: `slack: true` turns them on after `mmscan run`; `verdicts` and `changes` pick what is posted; `max_items` caps the message; `on_drop: true` also alerts on Cheaper results of any verdict. |

Optional `cash_fares.csv`, next to `config.yaml`, with columns
`origin,destination,cabin,month,fare_eur` (`month` as `YYYY-MM`). Matching
results get a cash fare, saving and value per mile. Bad rows are skipped
with a warning naming the line.

## Slack alerts

1. In Slack, create an app at <https://api.slack.com/apps> ("From scratch"),
   turn on **Incoming Webhooks**, and add a webhook to the channel you want.
2. Put the webhook URL in `.env` as `SLACK_WEBHOOK_URL=...`. It is a secret:
   never put it in `config.yaml`.
3. Set `notify.slack: true` in `config.yaml`.
4. Check the message with `uv run mmscan notify --dry-run`, then send it
   with `uv run mmscan notify`.

`mmscan run` then posts after each run, but only results that are on the
Shortlist, have a verdict in `notify.verdicts` (default Deal) and are New or
Cheaper than the previous run. A quiet run posts nothing, and so does the
very first run, which has no previous run to compare with. A Slack failure
is logged in the run log and does not fail the run.

If the tool runs in a cloud environment with a network allowlist, add
`hooks.slack.com` next to `seats.aero`.

## Getting told fast: schedule

seats.aero has no webhooks, and its cached data refreshes every few hours,
so polling more often than hourly finds little new. Two schedules cover it:

```cron
# Hourly: watchlist only, posts new or cheaper deals to Slack (2 calls).
7 * * * *  cd /path/to/mmscan && uv run mmscan watch >> data/watch.log 2>&1
# Daily: regions, fees for candidates, full report (about 4 + pages + 150 calls).
37 5 * * * cd /path/to/mmscan && uv run mmscan run   >> data/run.log 2>&1
```

That is roughly 48 + 160 calls a day, inside the 300 `api.daily_call_cap`
and the 1,000-call Pro allowance.

New and Cheaper compare each route, date and cabin with the last time any
earlier run saw it, not with one previous run. So hourly watch runs and the
daily run do not mark each other's results as New, and each deal is posted
once: New when first seen, Cheaper when its total drops 5% or more since it
was last seen.

## Findings

- **Live API:** `mmscan check` ran on 2026-10-12; see
  [`docs/api-findings.md`](docs/api-findings.md). Main finding: fees are in
  USD and the summary already carries them.
- **First scan (2026-10-12):** 36 calls for 26,386 region results and 3,931
  watchlist results (about 15 pages of 1,000 per region direction, 5 for the
  watchlist); about 30,300 distinct availabilities, 49,486 priced cabin
  results.
- **`include_filtered` comparison (2026-10-12, 31 calls):** with
  `include_filtered=true` the two region directions returned 30,320 distinct
  availabilities against 30,317 with the default: 5 extra and 2 missing, which
  is scan timing, not hidden data. Including them moved no route baseline
  (20th percentile and median shift 0.0% on all 32 Southeast Asia routes with
  15 or more samples). Miles & More hides essentially nothing, so the default
  `include_filtered: false` stays.
- **Fee spread per route (milestone 2):** pending a live enrich.
  `mmscan enrich` prints min, median and max fee per route and cabin.

## Tests

```bash
uv run pytest -q && uv run ruff check . && uv run ruff format --check .
```

Tests never touch the network.

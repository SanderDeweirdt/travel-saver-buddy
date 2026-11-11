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
| `mmscan scan` | Region pairs (Bulk Availability), then your watchlist items and trips (Cached Search, trips included) | One per page; 2 first pages plus 1 per watchlist item and trip leg |
| `mmscan enrich` | By hand: picks the cheapest 30% of region results (by miles) and fetches their trip details | Up to `enrich.max_calls` (50) |
| `mmscan score` | Total cost, baselines, flags and verdicts | 0 |
| `mmscan report` | Spreadsheet, Shortlist CSV and the terminal top 10 | 0 |
| `mmscan run` | Scan, score, fetch trip details for Shortlist results only, score again, report, notify; prints the planned calls first | Scan plus at most `enrich.max_calls` |
| `mmscan watch` | Watchlist items and trips only: scan (first `watch.max_pages` page per search), score against stored history, post new deals to Slack. For hourly runs | 1 per watchlist item and trip leg |
| `mmscan notify` | Posts the latest run's alerts to Slack (new deals, plus any older-style alerts that are switched on); nothing when there are none. `--dry-run` prints the message. `--test` posts a "Hello world" to check the webhook (reads no data) | 0 |
| `mmscan trips` | Best round trips per trip profile, from stored results (`--top N`) | 0 |
| `mmscan verify-add` | Records one hand check of a cached price against the live one (carrier, cached miles, live miles); feeds the dashboard's trust table | 0 |
| `mmscan vacuum` | Rewrites the tables so space freed by the purge goes back to the volume (Postgres `VACUUM FULL`; SQLite `VACUUM`). Locks each table while it runs; `cron.sh` does it monthly | 0 |
| `mmscan quota` | Calls left today (last `X-RateLimit-Remaining`) and calls made by mmscan today | 0 |

`enrich` and `score` work on the latest `scan` or `run`; `watch` runs are left
out of `enrich` because they hold only the watchlist. Every scoring run folds
what it saw into the stored price history and rebuilds the **current offers**:
the latest price we fetched for each route, date and cabin, whichever run saw
it last. `report`, the dashboard, trips and Slack all read those, so they
always agree. Get Trips results are cached per availability `ID` and
`UpdatedAt`, so a rerun does not pay for unchanged availabilities. If the
daily cap (`api.daily_call_cap`, default 300) is reached, the run stops,
keeps what it stored, is marked `partial`, and exits non-zero.

Reports go to `reports/mmscan_YYYY-MM-DD_HHMM.xlsx` (sheets Shortlist, All
results, Route stats, Run log) and `..._shortlist.csv`. The database is
`data/mmscan.db`; runs, calls and prices not seen for 180 days are deleted (per-run availabilities and results after 14 days, trip details after 30) at the start of each
scan.

## Tuning `config.yaml`

| Block | What it changes |
| --- | --- |
| `source`, `cabins`, `min_seats` | Program, cabins read from each result, seats you need. Fewer seats are kept but flagged. |
| `mile_cost_eur_cents` | What one mile costs you; turns miles into euros for the total cost. |
| `mr_point_value_eur_cents` | What one Amex Membership Rewards point is worth to you, in euro cents. A program under `programs` with `mr_per_mile` (points per mile after the transfer ratio, 1.5 for KrisFlyer at 3:2) costs `mr_per_mile` x this per mile, so awards bought with Amex points and Miles & More miles share one euro total. |
| `programs` | The one list of mileage programs besides Miles & More, keyed by seats.aero source id. Per program: `enabled` (you can book it; off means not requested and not shown), `within_region` (also scanned within Asia, where Miles & More returns nothing), `mr_per_mile` or `mile_cost_eur_cents`, `label`, `link_template`. Nothing else names a program: the scan asks for every enabled one. |
| `usd_to_eur` | Fixed rate for fees: seats.aero reports Miles & More fees in USD. Update it now and then. Without it the Shortlist stays empty. |
| `date_window` | Days from today to scan, recalculated each run. |
| `fx_to_eur` | Euro per unit of other fee currencies (SGD, THB, ...). Asia to Asia awards quote taxes in local currency; a currency missing here is unpriced and its flights are hidden. |
| `region_pairs` | Continent-level pairs for Bulk Availability: Europe to Asia, Asia to Europe and Asia to Asia. They set what the All flights page covers; the programs asked for each pair come from `programs` (between regions: Miles & More and every enabled one; within a region: the enabled `within_region` ones). Asia to Asia is read by the daily `run` only. |
| `subregions` | Airport lists that refine a continent, used by `benchmarks`. |
| `benchmarks` | Fallback ceilings per cabin and place pair, used when a baseline is thin. `chart_rate_miles` sets the chart-rate flag at 95%. |
| `relative` | `percentile_good` (deal threshold), `min_samples` (below this a baseline is unknown), `history_days` (a flight not seen for this long stops counting as on offer), `min_discount_pct` (a route or destination only counts as good when the total is also this % below its median; 0 = plain percentile cut). Lufthansa-group fares barely move by date, so a high value leaves few Deals. |
| `deals` | `min_saving_pct` (30): Best deals lists only flights at least this % below the usual price. `default_cabin` (`economy`): the cabin the All flights page opens on; `""` means all cabins. `by_ceiling: true` makes a result within its benchmark's `good_miles_max` and `fees_max_eur` a Deal even when the relative baselines say no. The right way to find deals on routes whose fare never moves. Check the ceilings against real fees: the PRD's 200 EUR economy limit is below almost every real fee. |
| `drops` | `min_pct`: Change shows Cheaper when a total fell this much since it was last seen. |
| `shortlist` | `scope: focus` limits the Shortlist, the CSV and Slack to results matching a benchmark; `all` keeps everything scored Deal or Worth a look. "All results" always has every result. |
| `prescreen.percentile` | Share of region results, cheapest first, that get their fees fetched. |
| `enrich.max_calls` | Get Trips calls per run: for `run` it caps trip details for Shortlist results; for `enrich` it caps the pre-screened candidates. Set to 0 to skip. |
| `value_per_mile_cents` | Bands for value per mile against a cash fare. |
| `api` | Page size, mixed-cabin filter, `include_filtered`, and the daily call cap. |
| `output` | Report folder and formats. |
| `watch.max_pages` | Pages per direction for `mmscan watch`. Results come cheapest first, so 1 page usually holds every deal. |
| `notify` | Slack alerts: `slack: true` turns them on after `mmscan run` and `watch`. `new_deals` (see Slack alerts below) posts each new flight at least `min_pct` (10) below its usual price. `verdicts` and `changes` pick the older Shortlist alerts (off by default: `verdicts: []`, `on_drop: false`); `max_items` caps the message. |
| `miles_and_more` | `link_template`: URL of a prefilled Miles & More award search. Placeholders `{origin} {destination} {date} {date_us} {cabin} {cabin_code} {adults}`. Gives every flight row an **M&M ↗** link for checking the price by hand. A link stored by seats.aero wins. The booking classes `B` (business) and `E` (economy) are confirmed by hand; `F` (first) is assumed. |

Optional `cash_fares.csv`, next to `config.yaml`, with columns
`origin,destination,cabin,month,fare_eur` (`month` as `YYYY-MM`). Matching
results get a cash fare, saving and value per mile. Bad rows are skipped
with a warning naming the line.

## Dashboard pages

| Page | What it shows |
| --- | --- |
| **All flights** (`/`, `/overview`) | The same rows with no saving cut: every flight on every route, one row per flight, whatever its saving. Routes without a usual price yet sit in the same table, marked "Building history". Same filters and the same 300-row limit. |
| **Flight watchlist** (`/watchlist`) | The flights you follow, added one by one: origin, destination and a departure date or range (stored in the database, up to 50). The page lists every item with how many flights fit it now and the cheapest; click one (`/watchlist/<id>`) to see the flights that fit its airports and dates, in any cabin. Every scan and `mmscan watch` also runs one Cached Search per item over the programs you can book, so a new item is filled at the next scan. `/shortlist` redirects here. |
| **Route** (`/route/...`) | Price history with the usual price as a dashed line, and today's results against it. |
| **Settings** (`/settings`) | The Miles & More mile value, the Amex point value, and per program: enabled or not, cost per mile, Amex points per mile. Saved in the database (table `settings`) and used by both the dashboard and the scanner, so a change needs no redeploy; `config.yaml` only lists the programs and their starting values. Saving recalculates every total; which programs are requested changes at the next scan. The only page that writes. Below that, a health section: quota, scanner health, the USD rate age, a table of live-to-cached mile ratios per carrier (from `mmscan verify-add`), Slack status and recent runs. |

"Usual price" is what the route normally costs with miles, from this tool's own history. It is not a cash ticket price.
**Unverified** marks Lufthansa-group (dynamic) prices: the cached miles can be far below the live price.
The older Shortlist alerts never post those, nor results older than 48 hours, unless `notify.unverified: true`. The new-deals alert does post dynamic prices, marked unverified.
Every flight row has an **M&M ↗** button that opens the matching search on miles-and-more.com (see `miles_and_more.link_template`), so a price can be checked by hand.
`usd_to_eur_date` records when you last checked the USD rate; past 30 days the dashboard and the run log warn.

The usual price is built from a month of stored results, so it is cached in memory for ten minutes per scan. The first page view after each scan is the slow one.

## Trips

A trip profile in `config.yaml` (`trips:`, example at the bottom of the file) describes a journey
you want to take: airports, departure and return windows, travellers, cabins, stop limit and an
optional budget. For each trip mmscan:

- searches only that trip's dates, one call per leg (so `watch` and `run` cost 2 extra calls per
  round trip), instead of hoping it shows up in a broader search;
- pairs every outbound with every return that fits the stay length (same airports unless
  `open_jaw: true`, same cabin) and ranks the pairs by what the whole party pays: miles at
  `mile_cost_eur_cents` plus fees, times the number of travellers;
- shows them on the dashboard's **Trips** page, with a budget marker and booking links;
- alerts on Slack when one of the best `alert_top` pairs is new or at least `drops.min_pct`
  cheaper than the last time it was seen. The first run alerts nothing.

Trip results come from the latest observation of each flight within `trip_freshness_hours`
(default 72). `mmscan trips` prints the same ranking in the terminal. Trip alerts follow the
`notify.slack` switch like the others.

## Fixed charts and dynamic prices

Miles & More prices Lufthansa Group carriers dynamically and everyone else on a fixed partner
chart. `dynamic_airlines` in `config.yaml` lists the dynamic ones (IATA codes; it has grown before,
keep it current).

- **Fixed-chart carriers:** a Deal when miles are at or under the benchmark's `chart_rate_miles`
  and fees inside `fees_max_eur`. Above the chart is no Deal.
- **Dynamic carriers:** no chart exists, so they are judged only against prices this tool has
  observed (the percentile and `min_discount_pct` rules). With too little history the verdict is
  **Unranked** and the row stays off the Shortlist and out of Slack. The cached figure can be far
  from the live price (seen live: 5,956 cached against about 17,000 on miles-and-more.com), so
  confirm on miles-and-more.com before acting.
- **Mixed routings** (a dynamic and a fixed carrier) are judged as dynamic, since the stored
  result does not say which carrier flies the long-haul segment.

## Slack alerts

1. In Slack, create an app at <https://api.slack.com/apps> ("From scratch"),
   turn on **Incoming Webhooks**, and add a webhook to the channel you want.
2. Put the webhook URL in `.env` as `SLACK_WEBHOOK_URL=...`. It is a secret:
   never put it in `config.yaml`.
3. Set `notify.slack: true` in `config.yaml`.
4. Check the message with `uv run mmscan notify --dry-run` (prints it, sends nothing), then send it
   with `uv run mmscan notify`. On Railway, set `SLACK_WEBHOOK_URL` on the scanner service.

`mmscan run` and `mmscan watch` then post after each scan. A quiet scan posts nothing, and so does the
very first run, which has no earlier run to compare with. A Slack failure is logged in the run log and
does not fail the run.

**New deals (the alert in use).** `notify.new_deals` posts each flight (origin, destination, date and
cabin) the first time any scan sees it, when it is already at least `min_pct` (default 10) below its
route's usual price. It covers every route, including Asia to Asia, not just the shortlist focus.

- `cabins` (default `[economy]`) limits it to those cabins.
- `unverified: true` (default) includes dynamic-carrier prices, marked "unverified" in the message.
  Set it to `false` for fixed-chart prices only.
- Routes without a usual price yet, and data older than 48 hours, never alert.
- Each message shows the saving against the usual price, carriers, stops, seats and a "Check on Miles &
  More" link. Up to `max_items` (10) are posted, best saving first; the rest are counted as "N more in
  the report".
- A route's usual price comes from stored results, so the first scan of a brand-new route (for example
  the first Asia to Asia run) compares flights with each other and can post a large batch.
- The 180-day window gains one new day a day on every route; those new dates count as new.

**Older Shortlist alerts** (`verdicts`, `changes`, `on_drop`) still exist but are switched off in the
shipped `config.yaml` (`verdicts: []`, `on_drop: false`). Turn them on to also get Deals and Cheaper
results from the Shortlist.

If the tool runs in a cloud environment with a network allowlist, add
`hooks.slack.com` next to `seats.aero`.

## Getting told fast: schedule

seats.aero has no webhooks, so scanning is polling. One daily schedule covers every region pair:

```cron
# Daily: all region pairs, fees for candidates, full report (about 50 calls).
7 11 * * * cd /path/to/mmscan && uv run mmscan run >> data/run.log 2>&1
```

That is roughly 50 calls a day, inside the 800 `api.daily_call_cap` and the 1,000-call Pro
allowance. `mmscan watch` (watchlist items only, 1 call each) still exists if you want an extra scan between
runs, but nothing schedules it.

New and Cheaper compare each route, date and cabin with the price it had
before the run that changed it, not with one previous run. So hourly watch
runs and the daily run do not mark each other's results as New, and each deal
is posted once: New when first seen, Cheaper when its total drops 5% or more
from its previous price.

## Price history

`observations` keeps one row per distinct price of a flight (route, date, cabin):
miles, fees as the API gave them, seats and when it was `first_seen` and
`last_seen`. A rescan at the same price only moves `last_seen`, so the table
grows with price changes, not with scans. Totals are never stored: they are
worked out from miles and fees with the current `mile_cost_eur_cents` and
`usd_to_eur`. `current_offers` is the scored copy of the newest price of every
flight and is rebuilt after each scoring run. The schema is versioned
(`schema_version`); a start applies any missing migrations, and the first one
that adds `observations` fills it from the old per-run `results`. The `results`
table is no longer written or read; it can be dropped once you are happy.

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

## Deploy on Railway

State lives in SQLite locally (`data/mmscan.db`) and in Postgres when `DATABASE_URL` is set. A
Railway deploy is a Postgres database, a cron **scanner** (`sh deploy/cron.sh`, hourly) and a
private read-only **dashboard** (`mmscan web`), both built from `Dockerfile`. Step-by-step
instructions and a first-deploy checklist: [docs/railway-deploy.md](docs/railway-deploy.md).

| Variable | Used by | Purpose |
| --- | --- | --- |
| `SEATS_AERO_API_KEY` | scanner, local | seats.aero Pro key |
| `SLACK_WEBHOOK_URL` | scanner, local | Slack alerts (when `notify.slack` is true) |
| `DATABASE_URL` | all | Postgres URL; unset means local SQLite |
| `DASHBOARD_PASSWORD` | dashboard | the one shared login password |
| `SESSION_SECRET` | dashboard | signs the session cookie |
| `MMSCAN_CONFIG` | dashboard | path to `config.yaml` (default `config.yaml`) |
| `MMSCAN_REPORT_DIR` | scanner | set by `cron.sh`; reports go to a temp dir |
| `DASHBOARD_INSECURE_COOKIES` | local | `1` allows the session cookie over plain http |
| `PORT` | dashboard | set by Railway |

Run the dashboard locally against the SQLite file:

```bash
DASHBOARD_PASSWORD=pick-one SESSION_SECRET=$(openssl rand -hex 32) \
  DASHBOARD_INSECURE_COOKIES=1 uv run mmscan web   # http://localhost:8000
```

`mmscan migrate-sqlite --from data/mmscan.db` copies local history into Postgres.

## Tests

```bash
uv run pytest -q && uv run ruff check . && uv run ruff format --check .
```

Tests never touch the network. Set `TEST_DATABASE_URL` to a scratch Postgres database (its
mmscan tables are dropped) to run the store tests on Postgres as well; without it they skip.


## Settings page

The Settings page edits the programs (bookable, also within Asia, costs) and the main config values: cabins, region pairs, date window, seats, API cap, watchlist, currency rates, the deal thresholds, the benchmarks and the Slack alerts. Saved values live in the database and win over `config.yaml`; scan settings reach the API requests at the next scan.

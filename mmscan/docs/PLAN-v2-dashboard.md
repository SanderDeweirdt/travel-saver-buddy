# Build plan: v2 dashboard ("Best deals")

Oct 13, 2026 · Implements the Best deals page from [`mockup-v2.html`](mockup-v2.html) and requirements R1, R5, R8
of [`PRD-v2.md`](PRD-v2.md). Server-rendered Jinja, same stack as today; no JS framework.

## What the user needs

Open the page, see the best ways to fly with miles ranked by how much cheaper they are than that route usually is:
price with miles (miles at 1.16 ct + fees) against the **usual price for the route**, per traveller count. The
usual price is the baseline mmscan already builds: the median total cost seen for that origin, destination and
cabin over `relative.history_days` (30). No cash fares are needed; `cash_fares.csv` stays an optional extra column.

## Starting point (read from the code)

| Already there | Where |
| --- | --- |
| Total cost per result, optional saving vs cash, value per mile, stored on each result; route median already computed for the shortlist | `scoring.py` (`Scored.cash_fare_eur`, `saving_eur`, `value_cents`), `results` table |
| Fixed-chart vs dynamic carrier logic | `config.pricing_model(carriers)`, already used in `queries.shortlist_view` |
| Data age per result | `queries.shortlist_view` (`age_h`) |
| Login, routes, templates, downloads, tests with `TestClient` | `web/app.py`, `web/templates/`, `tests/test_web.py` |
| Cash fares from a CSV, matched on origin, destination, cabin and month | `fares.py`, `cli._fares` |

## Gaps (what the mockup needs that does not exist)

1. **The baseline exists but is not on any list.** `queries.shortlist_view` already computes the route median
   (`baseline`, `samples`) but the page only shows it on the route page. Routes with fewer than
   `relative.min_samples` (15) results have no baseline and must be handled.
2. No page ranks by saving; the Shortlist ranks by verdict, then total cost.
3. No verdict based on saving against the baseline ("Great deal", "Above usual").
4. No traveller multiplier in the UI.
5. Dynamic-carrier results are not marked "Unverified" in the list.
6. The route page does not compare today's price with the usual price; Trips has no hero, 30-day trend or calendar.

## Milestones

Each one ships alone, passes `uv run pytest -q && uv run ruff check . && uv run ruff format --check .`, and
makes no API calls.

### M1. Baseline on every row (prerequisite)

- Expose the route median and sample count for every scored result, not only on the route page: one helper in
  `queries.py` that groups `history_rows` by `_route` once and returns `{route: (median, n)}`.
- Rule for thin data: below `relative.min_samples` there is no baseline, so no saving and no verdict; the row goes in
  a "Building history" list with its price and sample count.
- Keep the baseline honest: it is built from prices mmscan has seen, so include fixed-chart and dynamic carriers
  separately (group key gains the pricing model), otherwise a chart-rate fare is compared with dynamic fares.
- Tests in `test_scoring.py`/`test_deals.py`: median and sample count, thin route has no baseline, pricing models
  do not share a baseline.
- *Done when* a helper returns the baseline for every route in the latest run and the thin routes are counted.

### M2. Deals query and verdicts

- New `queries.deals_view(store, cfg, run_id, now, filters, pax)`: reuse `load_results`, keep results with a
  total cost and a baseline, add `save_eur` and `save_pct` against the route baseline, `value_cents`, `age_h`, `pricing`, then sort.
  Results with no baseline go in a separate "Building history" list so they are visible, not silently dropped.
- Saving verdict from new `config.yaml` keys `value.great_pct: 30` and `value.good_pct: 10`: Great, Good,
  Marginal (0 to good), Above usual (below 0). Validate on load like other keys.
- Sorts: percent saving (default), euro saving, lowest price, earliest date.
- Filters as query params: cabin, route, chart-price only, hide stale (default on), `pax` 1 to 4.
  Multiply miles, fees and totals by `pax`; seats below `pax` are hidden, unknown seats stay with a flag.
- Tests in `test_web.py`/new `test_deals.py`: ranking, verdict thresholds at the edges, negative saving, pax scaling,
  stale hidden, thin-history rows listed apart, dynamic marked unverified.

### M3. Page and navigation

- `templates/deals.html`: banner with the best verified deal, filter bar (plain GET form, works without JS), compact
  table with the columns in the mockup, the "How is this calculated?" note. Row link goes to the route page; the
  Book link is the stored booking link.
- Routes: `/` becomes Best deals; the current Shortlist moves to `/shortlist`; nav becomes Best deals, My trips,
  Data & alerts (Runs and Quota merge in M6). Keep `/reports/latest.xlsx` and `.csv`.
- Port the CSS from the mockup into `base.html` tokens; keep existing dark mode and `/healthz` unchanged.
- Banner picks the best deal with a fixed-chart carrier only.
- Tests: page renders with and without data, login still required, old Shortlist URL still works, no horizontal
  scroll is a manual check at 390 px.
- *Done when* the page matches the mockup on real data and loads in under a second.

### M4. Route page

- Show "below usual by X" on `route.html` from the same baseline; show the optional cash fare when one exists.
- Show median and 20th percentile lines on the history chart (`web/charts.py`).
- Tests: `route_history` returns the baseline and, when present, the optional cash fare.

### M5. Trips page upgrade (R5, R7, R8)

- Hero with whole-party price and budget bar from the existing trip pairing in `trips.py`.
- Best-price-per-scan series for the last 30 days: new `queries.trip_trend`, built from stored results.
- Cheapest-day calendar: group paired options by departure date, server-rendered grid.
- Mark results older than 48 h stale and leave them out of Slack (`notify.py`).
- Tests for trend and calendar grouping; one for the stale filter in `notify`.

### M6. Data & alerts page (R1, R2, R4)

- Merge Runs and Quota into one page; add scanner health, USD rate age (warn over 30 days) and the Slack switches
  as read-only status (the switches themselves stay in `config.yaml`).
- New small table `price_checks` (carrier, cached miles, live miles, checked on) and a CLI command
  `mmscan verify-add` to record a manual check; the page shows live-to-cached ratio per carrier. Needs both a
  SQLite and a Postgres migration in `store.py`.
- Flip `notify.slack` on for chart-price Deals and trip alerts only, after M1 and M3 have run for a few days.

## Order and effort

| Order | Milestone | Rough size | Why this order |
| --- | --- | --- | --- |
| 1 | M1 baseline on every row | small | Every saving figure depends on it |
| 2 | M2 deals query | medium | Pure Python, easy to test |
| 3 | M3 page and navigation | medium | First visible result; deploy here |
| 4 | M4 route page | small | Uses M1 and M2 |
| 5 | M5 trips upgrade | medium | Independent of M2 to M4 |
| 6 | M6 data and alerts | medium | Needs new storage; last because it changes the schema |

## Risks

- **"Usual" is what mmscan has seen, not the market.** A route that is always expensive looks normal. The page says
  so in its explainer and labels the column "Usual price", never "cash price".
- **Fixed-chart fares barely move**, so savings against their own median are small. `relative.min_discount_pct`
  already guards the Deal verdict; the page shows the real percentage and lets 30% and 10% decide the label.
- **New routes have no history.** They sit in "Building history" for roughly the first 15 scans of that route.
- **Dynamic carriers look like great deals** when cached miles are too low. They are marked Unverified, excluded from
  the banner and from Slack until M6 gives a measured ratio.
- **Schema change in M6** must work on SQLite and Postgres; test both (`TEST_DATABASE_URL`).
- **Moving `/` breaks bookmarks.** Keep `/shortlist`.

## Decisions

- Baseline: the existing route median of total cost (miles at 1.16 ct + fees), 30 days. No cash fare source.
- Verdict thresholds: Great at 30% below usual, Good at 10%, below 0 is "Above usual". Same for both cabins.

## Open questions

1. Should economy and business use the same thresholds? Kept the same for now.
2. Is a 30-day window right, given hourly watch scans and a daily full run? Configurable via `relative.history_days`.

# Build plan: v2 dashboard ("Best deals")

Oct 13, 2026 · Implements the Best deals page from [`mockup-v2.html`](mockup-v2.html) and requirements R1, R5, R8
of [`PRD-v2.md`](PRD-v2.md). Server-rendered Jinja, same stack as today; no JS framework.

## What the user needs

Open the page, see the best ways to fly with miles ranked by how much cheaper they are than paying cash:
price with miles (miles at 1.16 ct + fees) against the usual cash price for that route, per traveller count.

## Starting point (read from the code)

| Already there | Where |
| --- | --- |
| Total cost per result, saving vs cash, value per mile, all stored on each result | `scoring.py` (`Scored.cash_fare_eur`, `saving_eur`, `value_cents`), `results` table |
| Fixed-chart vs dynamic carrier logic | `config.pricing_model(carriers)`, already used in `queries.shortlist_view` |
| Data age per result | `queries.shortlist_view` (`age_h`) |
| Login, routes, templates, downloads, tests with `TestClient` | `web/app.py`, `web/templates/`, `tests/test_web.py` |
| Cash fares from a CSV, matched on origin, destination, cabin and month | `fares.py`, `cli._fares` |

## Gaps (what the mockup needs that does not exist)

1. **Cash prices are the weak link.** A fare must match an exact `YYYY-MM`, and the CSV is read only by the scanner.
   Without a match a result has no saving. The mockup's whole ranking depends on this.
2. No page ranks by saving; the Shortlist ranks by verdict, then total cost.
3. No verdict based on saving ("Great deal", "Cash is cheaper").
4. No traveller multiplier in the UI.
5. Dynamic-carrier results are not marked "Unverified" in the list.
6. The route page has no cash line; Trips has no hero, 30-day trend or calendar.

## Milestones

Each one ships alone, passes `uv run pytest -q && uv run ruff check . && uv run ruff format --check .`, and
makes no API calls.

### M1. Cash price coverage (prerequisite)

- Let `cash_fares.csv` accept `month` of `*` (any month) as a fallback, so one row per route and cabin is enough.
  Exact month wins. Add the rule to `CsvFareSource.fare` and `docs`/README.
- Count results with and without a cash price per run and put both numbers in the run log.
- Check that `cash_fares.csv` reaches the scanner on Railway (it is read from `config.yaml`'s folder, so it must be
  in the image). Commit a starter file with Sander's best-guess fares for the watchlist routes.
- Tests: `test_fares.py` for the wildcard and precedence; `test_scoring.py` for a result matched via wildcard.
- *Done when* a scan prints "cash price for N of M shortlist results" and the starter file covers every watchlist
  route in economy and business.

### M2. Deals query and verdicts

- New `queries.deals_view(store, cfg, run_id, now, filters, pax)`: reuse `load_results`, keep results with a
  total cost and a cash price, add `save_eur`, `save_pct`, `value_cents`, `age_h`, `pricing`, then sort.
  Results with no cash price go in a separate "No cash price yet" list so they are visible, not silently dropped.
- Saving verdict from new `config.yaml` keys `value.great_pct: 30` and `value.good_pct: 10`: Great, Good,
  Marginal (0 to good), Cash is cheaper (below 0). Validate on load like other keys.
- Sorts: percent saving (default), euro saving, lowest price, earliest date.
- Filters as query params: cabin, route, chart-price only, hide stale (default on), `pax` 1 to 4.
  Multiply miles, fees and totals by `pax`; seats below `pax` are hidden, unknown seats stay with a flag.
- Tests in `test_web.py`/new `test_deals.py`: ranking, verdict thresholds at the edges, negative saving, pax scaling,
  stale hidden, missing cash price listed apart, dynamic marked unverified.

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

- Add the usual cash price and "below usual by X" to `route.html`, using the cash fare for that route and cabin.
- Show median and 20th percentile lines on the history chart (`web/charts.py`).
- Tests: `route_history` returns the cash price when present and `None` otherwise.

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
| 1 | M1 cash price coverage | small | The page is empty or misleading without it |
| 2 | M2 deals query | medium | Pure Python, easy to test |
| 3 | M3 page and navigation | medium | First visible result; deploy here |
| 4 | M4 route page | small | Uses M1 and M2 |
| 5 | M5 trips upgrade | medium | Independent of M2 to M4 |
| 6 | M6 data and alerts | medium | Needs new storage; last because it changes the schema |

## Risks

- **Stale or wrong cash prices make every saving wrong.** Mitigation: show the date the fare file was last changed on
  the page, count results without a cash price, and mark wildcard-month fares as "typical".
- **Dynamic carriers look like great deals** when the cached miles are too low. They are marked Unverified,
  excluded from the banner and from Slack until M6 gives a measured ratio.
- **Schema change in M6** must work on SQLite and Postgres; test both (`TEST_DATABASE_URL`).
- **Moving `/` breaks bookmarks.** Keep `/shortlist` and redirect nothing else.

## Open questions

1. Where do usual cash prices come from: hand-typed CSV, or a table edited on the dashboard later?
2. Should "usual cash price" be per month, or one typical value per route and cabin (the wildcard in M1)?
3. Are the verdict thresholds (30% and 10%) right for a business cabin, where cash fares are far higher?

# One current price per flight

## Problem

Every page reads a different slice of the data. Shortlist, Best deals and All routes read the
latest scored *run*; Trips and Route history read the latest result per leg across runs; baselines
scan a month of results. A watch run holds only the watchlist and a full run holds the regions, so
the same flight can show different prices, ages and verdicts depending on the page.

What the user wants: for each route + date (+ cabin), the latest price we managed to fetch,
compared with what that route usually costs.

## Model

Three layers, facts first.

1. **`observations`** (facts, price history). One row per distinct *price state* of a flight key
   `origin|destination|date|cabin`. The state is `(miles, fees_minor, currency, fee_estimated,
   expired)`. A rescan that sees the same state bumps `last_seen` (and refreshes seats, times,
   booking link and `source_updated_at`) instead of adding a row; a changed state adds a row. A
   row therefore covers the span `first_seen .. last_seen`. `run_id` is the run that created it. If
   the same run scores a second time (score, enrich, score again) and the state changes, the run's
   own row is replaced rather than a new one added.
   - `last_seen`: when *we* last saw this price.
   - `source_updated_at`: seats.aero's `UpdatedAt`, the real age of the price.
   - Totals are never stored here. They are computed from miles and fees with the current config.
2. **`current_offers`** (derived, rebuilt after every scoring run). The newest observation of every
   key that is still fresh (`last_seen` within `relative.history_days`, date not in the past),
   scored together: totals, the "usual" price, flags, verdict and change. Every page reads this
   table; nothing page-facing takes a `run_id`.
3. **Usual price.** Across dates: the median total of the current offers on the same route, cabin
   and pricing group (fixed or dynamic), as `baseline.py` does today, once `relative.min_samples`
   is reached. The time-based variant (same date over time) is left for later; `observations`
   already holds the data for it.

`change` (New / Cheaper) means *changed in this run*: the key's newest observation was created by
the run being scored, and it has no earlier observation (New) or a lower total than the previous
state (Cheaper). Alerts for a run are the current offers that changed in that run, so a flight is
reported once.

## Schema changes

A `schema_version` table and numbered migrations replace `CREATE TABLE IF NOT EXISTS` as the only
schema mechanism. Migration 1 is the existing schema, so existing databases are stamped, not
rebuilt. Migration 2 adds `observations` and `current_offers`. Migration 3 backfills
`observations` from `results` (history collapsed into price states) and builds nothing else; the
next scoring run builds `current_offers`.

## Order of work

1. Migrations framework, `observations`, `current_offers` tables.
2. Record observations and rebuild `current_offers` in `score_run` (alongside `results`).
3. Backfill migration.
4. Move readers onto `current_offers` / `observations`: deals and shortlist pages, baselines, route
   history, trips, notify, report, enrich, CLI.
5. Stop writing `results`; it stays in the database, unread, for one release.

## Out of scope

- Marking a flight "gone" when a scan that should have covered it does not return it. Until then
  the existing 48 hour staleness filter on `source_updated_at` hides it.
- The time-based "usual" price.

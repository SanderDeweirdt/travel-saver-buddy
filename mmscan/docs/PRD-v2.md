# PRD: mmscan v2, the always-on award watcher

Oct 13, 2026 · @Sander · Status: draft for review

Supersedes the scope and "not now" list of [`PRD.md`](PRD.md) (v1, 11 Oct). v1's API reference, scoring rules and
report layout still apply unless this document says otherwise. Live API behaviour that differs from v1 is in
[`api-findings.md`](api-findings.md).

## Summary

mmscan watches Miles & More award availability on seats.aero, scores every result against what that route normally
costs, and tells Sander when a good seat for a trip he wants appears. v1 was a command you ran by hand. v2 runs
itself on Railway, remembers every price it has seen, shows the results in a private dashboard, and posts to Slack.

## Problem

Miles & More award prices for Lufthansa Group flights move with date and demand, and good seats vanish within days.
Checking miles-and-more.com by hand across five departure airports, four destinations and 330 days is not
realistic. seats.aero has the data but no alerts, no price history and no notion of "cheap for this route".

## Goals

1. Find out within about an hour when an award that is cheap for its route, or fits a planned trip, shows up.
2. Rank by what the flight really costs per person (miles at Sander's cost per mile, plus fees), not by miles alone.
3. Judge each result with the right yardstick: a fixed partner chart or observed history, depending on the carrier.
4. Make results easy to browse and share with Georgia without installing anything: one private web page.
5. Stay inside the seats.aero Pro allowance (1,000 calls/day) and its personal-use terms, with a hard cap.

## Non-goals

- Booking, or logging in to Miles & More.
- Live prices. All data is seats.aero's cache; every surface says so.
- Other mileage programs (the `source` stays configurable; only `lufthansa` is tested).
- Cash fares from an API (none exists). Manual `cash_fares.csv` stays optional.
- Multiple users, public access or any commercial use. One shared password, personal use only.

## Users

Sander (owner, configures and deploys) and Georgia (reads the dashboard and Slack alerts). Both plan long-haul
family travel from Belgium and Germany to Southeast Asia, starting with Philippines trips.

## Current product (shipped)

| Area | What exists |
| --- | --- |
| Scan | `scan`, `run`, `watch`: regions via Bulk Availability, watchlist via Cached Search with trips |
| Pricing | Fees come from the summary object in USD, converted at a fixed `usd_to_eur`; Get Trips only for Shortlist results |
| Scoring | Route and destination percentiles, benchmark ceilings, chart-rate flag, value per mile; separate logic for fixed-chart and dynamic carriers |
| History | SQLite locally, Postgres on Railway; 180-day retention; New/Cheaper compared with the last time each result was seen |
| Trips | Trip profiles: narrow searches per leg, round-trip pairing, whole-party price, budget marker, alerts |
| Dashboard | FastAPI: Shortlist, Trips, route history, Runs, Quota, xlsx/csv downloads, shared-password login with rate limiting |
| Alerts | Slack webhook (built, currently off) |
| Deploy | Railway: daily 05:07 UTC cron (`watch` + `run`), web service, Postgres |

## Requirements for the next version

Priority: P0 must have for v2 to be trusted, P1 should have, P2 later.

### P0: trustworthy numbers

- **R1. Cached versus live gap.** The tool cached 5,956 miles where miles-and-more.com showed about 17,000 for the same
  flight. Until this is understood, dynamic-carrier results must carry an "unverified" mark everywhere they appear.
  Measure the gap on a sample of at least 20 results and record the ratio per carrier in `api-findings.md`.
  *Done when* the documented gap per carrier exists and the dashboard says which prices are chart-based and which are not.
- **R2. Re-enable Slack.** Alerts were switched off until cached mileage is trusted. Turn them on for fixed-chart
  Deals and trip alerts first, dynamic carriers only after R1.
  *Done when* a quiet hour posts nothing, a new fixed-chart Deal posts once, and the same Deal is not posted again
  unless its total drops by `drops.min_pct`.
- **R3. Realistic ceilings.** The PRD v1 economy ceiling of 200 EUR in fees sits below almost every real fee
  (30 to 700 EUR). `config.yaml` already uses 280 EUR; replace the placeholders with ceilings derived from at least
  30 days of stored route statistics.
  *Done when* each benchmark's ceiling cites the statistic it came from.
- **R4. Currency.** Fees arrive in USD and are converted at a hand-edited rate. Either fetch the rate daily from a
  documented source or fail the run's Shortlist loudly when the rate is older than 30 days.

### P1: planning trips

- **R5. Trip-first dashboard.** The Trips page is the default landing page when at least one trip profile exists.
  Each trip shows its best five round trips, the budget marker, the price trend of the best option over the last
  30 days, and one-click booking links.
- **R6. Trip profiles outside the repo.** Profiles live in `config.yaml`, so every change is a commit and a redeploy.
  Allow editing them from the dashboard (stored in Postgres, validated by the same code as the file).
  *Done when* adding a trip needs no git commit and a bad profile is rejected with the key named.
- **R7. Best-day view.** For a trip with flexible dates, show the cheapest total per departure day as a calendar,
  so the cheap weeks are visible at a glance.
- **R8. Stale-data guard.** Any result whose `UpdatedAt` is over 48 hours old is marked stale on the dashboard and
  excluded from Slack.

### P2: later

- Per-user logins for Georgia, with her own alert preferences.
- Premium economy, if seats.aero adds it to the `lufthansa` source.
- A second program (for example Flying Blue) behind the existing `source` setting.
- An automatic cash-fare source, so saving and value per mile are filled without a CSV.

## Success metrics

| Metric | Target |
| --- | --- |
| Time from a deal appearing in seats.aero to a Slack post | Under 90 minutes (hourly watch plus cache refresh) |
| API calls per day | Under 300, never above the 1,000 allowance |
| Slack false alarms: posted Deals that fail the check on miles-and-more.com | Under 20% after R1 and R3 |
| Missed alerts: a trip option on the dashboard that was never posted | 0 |
| Scanner runs that fail per week | Under 2 |

## Constraints and risks

- **Quota.** 1,000 calls/day on a Pro key; `daily_call_cap` (300) is counted in the database and holds across runs.
  Hourly `watch` costs 2 calls plus 2 per trip round trip.
- **Terms.** Personal, non-commercial use; the data is not redistributed. The repository is public, so recorded live
  responses stay git-ignored and the dashboard stays behind a login on every route except `/healthz`.
- **Data quality.** Cached, not live. Per-cabin seat counts are often 0 and are treated as unknown. Dynamic carrier
  prices may be far from live prices (R1).
- **Carrier lists drift.** `dynamic_airlines` has grown before and WK (Edelweiss) is reported by one source only.
  A wrong list makes fixed-chart carriers look dynamic or the reverse; review it each quarter.
- **Access.** seats.aero does not enable the API for every Pro account. `mmscan check` proves it (4 calls).
- **Railway config as code** is deprecated for new services after 2026-12-01; settings are applied in the service UI.
- **Cost.** Railway bills by usage; check it after the first week.

## Open questions

1. Is R1 best solved by sampling manually, or by a scheduled `mmscan verify` that opens the booking link? The second
   needs a Miles & More login, which is out of scope today.
2. Should trip alerts include dynamic-carrier options before R1 is done, flagged as unverified, or wait?
3. Does Georgia want Slack, or e-mail, or just the dashboard?
4. The fee-spread-per-route measurement from v1 milestone 2 is still pending. Is the median-fee estimate still needed
   now that summary objects carry fees?

## Rollout

1. R1 and R3 first: measurement only, no code risk.
2. R2 and R4 behind `notify.slack` and a config check.
3. R5, R7 and R8 as dashboard changes, one deploy each.
4. R6 last, because it moves configuration into the database.

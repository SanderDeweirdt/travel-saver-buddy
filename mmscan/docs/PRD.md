# PRD: Miles & More award scanner

Oct 11, 2026 · @Sander

> Partly superseded by [`PRD-v2.md`](PRD-v2.md): scheduling, notifications and a web UI are now built, and the dashboard ranks against the route's usual price. The API reference and scoring rules below still apply.

A command-line tool that pulls Miles & More award availability from the seats.aero API in bulk, scores every result against configurable benchmarks, and writes a ranked shortlist to a spreadsheet. This document is the build brief for Claude Code; start at "Build order".

## Scope

The tool answers one question: which Miles & More awards in the seats.aero data are cheap compared with what that route normally costs.

In scope for v1:

- Pull cached Miles & More availability (seats.aero source `lufthansa`) for configured region pairs and date windows.
- Pull a watchlist of specific airport pairs.
- Store every run locally so prices can be compared across runs.
- Turn every result into a total cost in euros per person: miles at the user's cost per mile, plus the cash co-payment. Score that total against the route, the destination and a fallback ceiling.
- Fetch flight-level detail for every candidate: taxes and surcharges, carriers, flight numbers, stops, booking link. Nothing reaches the shortlist without its cash co-payment.
- Write a ranked spreadsheet and print a short terminal summary.
- List what is new or cheaper since the previous run.

Out of scope for v1:

- Booking, or logging in to Miles & More.
- Other mileage programs. Keep the source configurable, but only `lufthansa` is tested.
- Live Search. It is not available to Pro API keys.
- Automatic cash fares. The seats.aero API has no cash ticket prices. v1 reads fares the user enters by hand, behind an interface a fare source can plug into later.
- A web UI, notifications and scheduling. These are candidates for v2.
- Commercial or shared use. The API key is for personal, non-commercial use.

Alternative for one-off questions: seats.aero also offers an MCP server at `https://seats.aero/mcp`. This tool exists for repeatable bulk scoring with history, which ad hoc queries do not give.

## Decisions to confirm

These defaults are assumptions. Every one lives in the config file, so Claude Code can build with them and Sander can change them later without code changes.

| Decision | Default | Note |
| --- | --- | --- |
| Region pairs | Europe to Asia and Asia to Europe | The API only knows six continent-level regions |
| Watchlist origins | MUC, FRA, ZRH, VIE, BRU | Lufthansa-group prices vary by departure city |
| Watchlist destinations | SIN, KUL, BKK, MNL | Edit freely |
| Cabin | Economy and business | The `lufthansa` source carries economy, business and first, not premium economy |
| Seats needed | 2 | Results with fewer seats are kept but flagged |
| Date window | Today to 330 days out | Rolling, recalculated each run |
| Fallback ceiling, business, Europe to Southeast Asia | 60,000 miles and 450 EUR fees, one-way | Used only when a route or destination has too little data |
| Fallback ceiling, economy, Europe to Southeast Asia | 35,000 miles and 200 EUR fees, one-way | Placeholder set below the chart rate; replace it once the tool has its own statistics |
| Chart-rate marker | 100,000 miles in business and 42,500 in economy, one-way | Half the official return price for partner awards; shown as a flag only, because a chart-rate award with low fees can still win on total cost |
| Cost of a mile | 1.16 euro cents | Sander's purchase price; turns miles into euros |
| Results priced with fees per run | Every watchlist result, plus up to 150 region results | Watchlist fees come free with the search; each region result costs one API call |
| Mixed-cabin itineraries | Excluded | API default, `min_cabin_pct=100` |
| Stack | Python 3.12, uv, SQLite | Single user, runs on a laptop or a home server |
| Output | One .xlsx per run, plus CSV | No Google Sheets integration in v1 |
| How it runs | On demand from the terminal | Scheduling is v2 |

## How it works

One run is six steps. Steps 1, 2 and 4 call the API; the rest work from the local database and can be repeated for free.

1. **Scan regions.** Call Bulk Availability once per region pair and direction, with `take=1000`. Page with `skip` and `cursor` until `hasMore` is false. Deduplicate by `ID`. These results carry miles but no fees. With more than one cabin configured, send no cabin filter and read each configured cabin from the same objects.
2. **Scan the watchlist.** Call Cached Search with the watchlist origins and destinations as comma-separated lists, `sources=lufthansa`, `order_by=lowest_mileage` and `include_trips=true`. The trips arrive in the same response, so every watchlist result has its cash co-payment at no extra call. Run both directions, with the same cabin rule as step 1.
3. **Pre-screen.** Rank the region results on miles alone, per route and per destination, separately for each cabin, and keep the cheapest 30% as candidates.
4. **Enrich.** Call Get Trips for each candidate, cheapest first, up to `enrich.max_calls` (default 150). Skip any availability whose `UpdatedAt` has not changed since its trips were stored. Candidates left over are counted in the run log and picked up by the next run. One Get Trips call prices every cabin of that availability.
5. **Score.** Compute the total cost of every priced result, build the route and destination baselines, and apply the rules in "Scoring".
6. **Report.** Write the spreadsheet and CSV, print the top 10 to the terminal, and list what is new or cheaper than the previous run.

Commands, with `mmscan` as the working package and CLI name:

| Command | What it does | API calls |
| --- | --- | --- |
| `mmscan check` | Four small calls to confirm the key works and see what the live responses contain; saves the raw JSON as test fixtures | 4 |
| `mmscan scan` | Steps 1 and 2 | Depends on result volume; logged per run |
| `mmscan enrich` | Steps 3 and 4 | Up to 150 |
| `mmscan score` | Step 5 | 0 |
| `mmscan report` | Step 6 | 0 |
| `mmscan run` | All steps in order | Sum of the above |
| `mmscan quota` | Calls left today, from the last X-RateLimit-Remaining response header, and calls made by this tool | 0 |

Every command accepts `--config PATH` and `--dry-run`. A dry run prints the requests it would start with and sends nothing; page counts are only known once a scan runs.

## Configuration

All behaviour comes from one `config.yaml`. The API key is the only setting kept outside it, in the environment variable `SEATS_AERO_API_KEY`, loaded from a git-ignored `.env`.

```yaml
source: lufthansa
cabins: [economy, business]
min_seats: 2

# What one mile costs you, in euro cents. Turns miles into euros.
mile_cost_eur_cents: 1.16

date_window:
  start_offset_days: 0
  end_offset_days: 330

region_pairs:
  - {origin: Europe, destination: Asia}
  - {origin: Asia, destination: Europe}

watchlist:
  origins: [MUC, FRA, ZRH, VIE, BRU]
  destinations: [SIN, KUL, BKK, MNL]
  both_directions: true

# The API's regions are continents. Subregions refine them by airport list.
subregions:
  southeast_asia: [SIN, KUL, BKK, MNL, CGK, SGN, HAN, DPS, HKT, PEN, CEB]

# Fallback ceilings, used when a baseline has too little data.
# A place in "between" is an API region name or a subregion key.
# chart_rate_miles is half the official return price for partner awards.
benchmarks:
  - name: economy_europe_southeast_asia
    cabin: economy
    between: [Europe, southeast_asia]
    good_miles_max: 35000
    chart_rate_miles: 42500
    fees_max_eur: 200
  - name: business_europe_southeast_asia
    cabin: business
    between: [Europe, southeast_asia]
    good_miles_max: 60000
    chart_rate_miles: 100000
    fees_max_eur: 450

relative:
  percentile_good: 20
  min_samples: 15
  history_days: 30

prescreen:
  percentile: 30

enrich:
  max_calls: 150

value_per_mile_cents:
  good: 2.0
  fair: 1.5
  poor: 1.2

api:
  take: 1000
  min_cabin_pct: 100
  include_filtered: false
  daily_call_cap: 300

output:
  dir: ./reports
  formats: [xlsx, csv]
```

Validate the config on load and fail with a message that names the bad key. Unknown airports in `subregions` or `watchlist` are a warning, not an error.

Optional second input, `cash_fares.csv`, with columns `origin, destination, cabin, month, fare_eur` (`month` as YYYY-MM). When a row matches a result, the report shows the cash fare, the saving against it and the value per mile. When none matches, those columns stay empty. Read the file through a small fare-source interface so an automatic source can replace it later.

## Scoring

A result is a deal when its total cost is low for its route and low for its destination. Total cost is what the flight really costs per person, so a low mileage price with a heavy surcharge cannot pass as a bargain.

Total cost in euros = miles x cost per mile + fees. Example: 42,500 miles at 1.16 ct is 493 EUR; with 50 EUR in fees the total is 543 EUR.

Each priced result is one route, date and cabin. It gets these flags:

| Flag | Condition |
| --- | --- |
| `route_good` | Total cost at or below the 20th percentile for the same origin, destination and cabin |
| `destination_good` | Total cost at or below the 20th percentile across all origins in the same region to that destination, same cabin |
| `ceiling_good` | Miles at or below `good_miles_max` and fees at or below `fees_max_eur` of the matching benchmark |
| `seats_ok` | Remaining seats at or above `min_seats` |
| `direct` | The trip has no stops |
| `chart_rate` | Miles at or above 95% of `chart_rate_miles`; information only |
| `value_band` | Good, fair or poor, from value per mile; needs a cash fare |

The flags combine into one verdict per result:

| Verdict | Rule |
| --- | --- |
| Deal | `route_good` and `destination_good`, with `seats_ok` |
| Worth a look | Exactly one of `route_good` or `destination_good` |
| Skip | Everything else |

Rules behind the flags:

- **Total cost.** Per adult, one-way. Miles come from the trip's `MileageCost`, fees from its `TotalTaxes`, and the cost per mile from `mile_cost_eur_cents`.
- **Which trip.** One availability can hold several trips. Use the trip with the lowest total cost in the target cabin that meets `min_seats`. If none meets it, use the lowest total cost and set `seats_ok` to false.
- **Baselines.** Use every result for the same cabin from the current run plus the stored runs of the last `history_days`. The route baseline groups by origin and destination. The destination baseline groups by origin region and destination.
- **Results without fees.** Region results that were not enriched enter the baselines with an estimated fee: the median fee of priced results on the same route. Mark them as estimated. They count toward baselines but never appear on the Shortlist. A route with no priced result stays out of the destination baseline.
- **Thin data.** A baseline with fewer than `min_samples` results is unknown. `ceiling_good` then stands in for that layer. When no benchmark matches either, the result can reach Worth a look at most.
- **Unavailable cabins.** A mileage cost of `"0"`, empty or null means the cabin is not available. Only use a cabin whose `Available` flag is true.
- **Seat count of zero.** Treat 0 remaining seats on an available cabin as unknown, not as sold out, and show it as unknown in the report.
- **Against cash.** With a cash fare, show the saving (cash fare minus total cost) and the value per mile ((cash fare minus fees) divided by miles, in euro cents). Bands come from `value_per_mile_cents`. Without a cash fare these stay blank and the verdict is unaffected.
- **Ranking.** Verdict first, then total cost ascending, with direct flights ahead of connections on ties.
- **New or cheaper.** New means the route, date and cabin did not appear in the previous run. Cheaper means its total cost dropped by 5% or more.
- **Infants.** Not modelled. All figures are per adult.

Two assumptions to test:

- **Fees are stable within a route.** The fee estimate relies on it. Milestone 2 reports the spread of fees per route; if it is wide, drop the estimate and build baselines from priced results only.
- **Hidden expensive results.** By default the API leaves out expensive dynamically priced results (`include_filtered=false`). That makes the stored distribution look cheaper than reality, so the percentiles are stricter than they seem. In milestone 1, run one scan each way, record how the counts differ in the README, and keep the default unless the difference is large.

## Report

Each run writes `reports/mmscan_YYYY-MM-DD_HHMM.xlsx` with four sheets, and the Shortlist sheet again as CSV.

| Sheet | Contents |
| --- | --- |
| Shortlist | Priced results with verdict Deal or Worth a look, ranked by total cost |
| All results | Every result from this run, with a filter row and a column saying whether its fee is actual or estimated |
| Route stats | Per route and per destination, by cabin: sample count, then minimum, 20th percentile, median and maximum total cost, and the median fee |
| Run log | Run time, config used, API calls made, result counts, candidates not yet priced, warnings |

Shortlist columns, in this order:

| Column | Source |
| --- | --- |
| Verdict | Scoring |
| Change | New, Cheaper or blank, against the previous run |
| Date | Availability `Date` |
| Origin, Destination | `Route.OriginAirport`, `Route.DestinationAirport` |
| Cabin | Trip `Cabin` |
| Miles | Trip `MileageCost` |
| Miles cost (EUR) | Miles x `mile_cost_eur_cents` |
| Fees (EUR) | Trip `TotalTaxes`, converted from minor units |
| Total cost (EUR) | Miles cost plus fees |
| Cash fare (EUR) | `cash_fares.csv`, blank when nothing matches |
| Saving vs cash (EUR) | Cash fare minus total cost |
| Value per mile (ct) | (Cash fare minus fees) divided by miles |
| Route percentile | Where the total cost sits in the route baseline, 0 to 100 |
| Destination percentile | Where it sits in the destination baseline, 0 to 100 |
| Seats | Trip `RemainingSeats`, or "unknown" |
| Stops | Trip `Stops` |
| Carriers | Trip `Carriers` |
| Flights | Trip `FlightNumbers` |
| Departs, Arrives | Trip `DepartsAt`, `ArrivesAt`, shown as airport local time |
| Flags | `chart_rate` and `ceiling_good` when true |
| Data age (h) | Hours since the availability's `UpdatedAt` |
| Booking link | Primary entry of `booking_links` from Get Trips |

Formatting: freeze the header row, turn on filters, colour the Verdict cell (green Deal, amber Worth a look), and format miles with thousands separators. Results whose data is older than 48 hours are marked "stale" in the Data age column.

The terminal summary prints the run totals and the top 10 Shortlist rows as a plain table.

## seats.aero API reference

Everything below was read from the seats.aero developer docs on 11 October 2026. Before coding, fetch [the docs index](https://developers.seats.aero/llms.txt) and re-check; where a live response differs from this section, the live response wins.

- Base URL: `https://seats.aero/partnerapi/`
- Auth: API key in the `Partner-Authorization` header on every request.
- All three endpoints are GET with query parameters and return JSON. Every response carries an X-RateLimit-Remaining header with the calls left today.

| Endpoint | Use | Parameters |
| --- | --- | --- |
| [`/availability`](https://developers.seats.aero/reference/get-availability.md) | Bulk Availability: many results from one program | `source` (required), `cabin`, `start_date`, `end_date`, `origin_region`, `destination_region`, `take`, `cursor`, `skip`, `include_filtered`, `min_cabin_pct` |
| [`/search`](https://developers.seats.aero/reference/cached-search.md) | Cached Search: specific airports | `origin_airport` (required), `destination_airport` (required), `start_date`, `end_date`, `sources`, `cabins`, `order_by`, `only_direct_flights`, `carriers`, `include_trips`, `minify_trips`, `take`, `cursor`, `skip`, `include_filtered`, `min_cabin_pct` |
| [`/trips/{id}`](https://developers.seats.aero/reference/get-trips.md) | Get Trips: flight-level detail for one availability `ID` | `include_filtered`, `min_cabin_pct` |

Parameter values:

- `cabin`: one of `economy`, `premium`, `business`, `first`.
- `origin_region`, `destination_region`: one of `North America`, `South America`, `Africa`, `Asia`, `Europe`, `Oceania`.
- `take`: 10 to 1000, default 500.
- Dates: `YYYY-MM-DD`.
- `origin_airport`, `destination_airport`, `sources`, `cabins`, `carriers`: comma-separated lists.
- `order_by=lowest_mileage` returns the cheapest results first.
- `min_cabin_pct`: 0 to 100, default 100, which excludes any itinerary with distance flown below the reported cabin.

Cached Search documents this response envelope: `data` (array), `count`, `hasMore`, `cursor`. The Bulk Availability page documents no response body; it is expected to match, so confirm it in milestone 0.

Availability object, one per route, date and program:

- `ID`, `RouteID`, `Date`, `ParsedDate`, `Source`, `CreatedAt`, `UpdatedAt`
- `Route`: `ID`, `OriginAirport`, `OriginRegion`, `DestinationAirport`, `DestinationRegion`, `NumDaysOut`, `Distance`, `Source`
- Per cabin, with prefix `Y`, `W`, `J` or `F`: `Available` (boolean), `MileageCost` (string), `RemainingSeats` (integer), `Airlines` (string such as "AA, B6"), `Direct` (boolean). Example: `JMileageCost`.
- `AvailabilityTrips`: null unless `include_trips=true` on Cached Search. With it, each availability carries its trips, taxes included, at no extra call. Bulk Availability has no such parameter.

Trip object, from Get Trips:

- `ID`, `AvailabilityID`, `Cabin`, `MileageCost` (integer), `TotalTaxes` (integer), `TaxesCurrency`, `TaxesCurrencySymbol`, `RemainingSeats`, `Stops`, `Carriers`, `FlightNumbers`, `DepartsAt`, `ArrivesAt`, `TotalDuration`, `Source`, optional `MixedCabinPct`
- `AvailabilitySegments`: per flight `FlightNumber`, `FareClass`, `AircraftCode`, `AircraftName`, `OriginAirport`, `DestinationAirport`, `DepartsAt`, `ArrivesAt`, `Distance`, `Order`
- Top level of the response: `booking_links`, each with `label`, `link`, `primary`.

Things that will bite:

- **Types differ.** Summary mileage costs are strings; trip mileage costs are integers. Per-cabin fields can be null.
- **Taxes are in minor units.** The docs describe `TotalTaxes` of 1290 as 12.90. `TaxesCurrency` can be an empty string; store the raw value and the currency, and flag an empty currency in the run log instead of guessing.
- **No taxes on the summary object in the documented schema.** Fees come from Get Trips. If the live summary response turns out to carry tax fields, use them and save the calls.
- **Times are airport local time** even though they end in `Z`. Do not convert them as UTC.
- **Pagination.** Set `skip` to the number of results already retrieved and `cursor` to the value from the first response. Objects can repeat across pages; deduplicate by `ID`.
- **Get Trips returns every cabin** for that availability. Filter on `Cabin`.
- **A 404 from Get Trips** means the availability is gone. Mark the result expired and continue.
- **`TotalDuration` has no documented unit.** The example values look like minutes; confirm against a real trip.
- **The `lufthansa` source** is listed with cabins Y, J and F, seat counts, and trip data.
- **Error responses are only partly documented.** The help article says 401 or 403 points to a missing, invalid or regenerated key or a malformed request, and that requests are rejected once the daily allowance is used up, without naming that status code. Treat 401 and 403 as fatal, with a message that API access may not be enabled for the account. Treat 429 and 5xx as retryable with backoff, unless the remaining-calls header is zero.

## Constraints

- **Quota.** A Pro key allows up to 1,000 API calls per day, resetting at midnight UTC. It is a daily allowance, not a per-second rate limit. Read the X-RateLimit-Remaining header after each call and treat it as the truth. Count every call in the local database and stop with a clear message at `daily_call_cap` (default 300), so a bug cannot burn the day's allowance.
- **Pacing and retries.** Send requests one at a time, at most two per second. Retry timeouts, 429 and 5xx up to three times with exponential backoff, and honour a `Retry-After` header when one is present.
- **Secrets.** Read the key from the environment only. It must never appear in the config, logs, fixtures, reports or git history. Redact the header in debug output.
- **Terms of use.** The key is for personal, non-commercial use. Do not publish or redistribute the data.
- **Access is not guaranteed.** seats.aero does not enable the API for every Pro account or country. `mmscan check` exists to find that out before anything else is built on it.
- **Cached, not live.** Every report carries the line "Cached data. Confirm price and seats on miles-and-more.com before acting." seats.aero may also miss availability that Miles & More shows.
- **Storage.** One SQLite file at `./data/mmscan.db` with tables for runs, availabilities, trips and API calls. Keep the raw JSON of each row so parsing can be fixed without new calls. Delete rows older than 180 days.
- **Logging.** One line per request: endpoint, parameters, status, duration, results returned.
- **Tests.** pytest, with no network access. Use recorded responses with the key stripped. Cover string, null and `"0"` mileage costs, pagination with duplicate IDs, every scoring rule, the percentile fallback, tax conversion and config validation.
- **Platform.** macOS and Linux, Python 3.12, no background services.

## Build order

Build in five milestones and stop after each one. Milestone 0 is a gate: it proves the account has API access and shows what the live responses contain, before any design depends on them.

| Milestone | Build | Done when |
| --- | --- | --- |
| 0. Access check | Repo scaffold (uv, ruff, pytest, `.gitignore`, `.env.example`). `mmscan check` makes four calls: Bulk Availability with `source=lufthansa`, `cabin=business`, `origin_region=Europe`, `destination_region=Asia`, `take=10`; Get Trips for the first `ID`; Cached Search for MUC to SIN with `sources=lufthansa`, `include_trips=true`, `take=10`; the same search with `minify_trips=true`. | All four raw responses are saved as fixtures with the key stripped. The README lists every difference from this PRD: envelope, tax fields on the summary object, whether minified trips keep `TotalTaxes`, the `TaxesCurrency` value, whether taxes are per passenger, and the `TotalDuration` unit. Total cost: 4 calls. |
| 1. Scan and store | Config loading and validation, API client (pagination, deduplication, retries, call counter), SQLite schema, `scan` for regions and for the watchlist with trips, `quota`, `--dry-run`. | A scan of the default config finishes under the daily cap. Every watchlist result is stored with its trips and fees. The call count per run is logged. The `include_filtered` comparison is written up in the README. |
| 2. Pre-screen and enrich | Candidate selection on miles, `enrich`, a trip cache keyed on availability `ID` and `UpdatedAt`, tax conversion. | Up to 150 candidates are priced in at most 150 calls. A second run on the same data makes no Get Trips call for unchanged availabilities. A 404 marks the result expired without stopping the run. The README reports the spread of fees per route. |
| 3. Score and report | Total cost, both baselines, the fee estimate, `score`, `report`, the four-sheet spreadsheet and CSV, `cash_fares.csv`. | Every scoring rule has a unit test. Every Shortlist row has actual fees and a total cost. The spreadsheet opens cleanly in Excel and LibreOffice. Run log totals match the database. |
| 4. Diff and full run | New and Cheaper detection, `mmscan run`, README with setup, usage and how to tune the config. | Two runs in a row produce a filled Change column. A fresh clone runs end to end in under 10 minutes by following the README. |

Not now: scheduling, notifications, other mileage programs, an automatic cash fare source.

Working rules for Claude Code:

- After each milestone, summarise what was built and what the live API showed, then wait for a go-ahead.
- Before any command that calls the live API, state how many calls it will make. `mmscan check` is the only one that may run without asking.
- Do not invent API fields. If a field this PRD relies on is missing from a live response, stop and report it.
- Dependencies allowed without asking: httpx, typer, pydantic, pyyaml, openpyxl, python-dotenv, pytest, ruff. Ask before adding others.
- Keep one module per concern: config, client, store, scoring, enrich, report, cli.
- Commit at the end of each milestone. Never commit `.env`, the database or reports.

## Sources

API behaviour, opened on 11 October 2026:

- [Getting Started](https://developers.seats.aero/reference/getting-started-p.md): base rules, auth header, Pro access, MCP server
- [Concepts](https://developers.seats.aero/reference/concepts-copy.md): sources table, availability and trip objects, mixed cabin, pagination
- [Bulk Availability](https://developers.seats.aero/reference/get-availability.md)
- [Cached Search](https://developers.seats.aero/reference/cached-search.md)
- [Get Trips](https://developers.seats.aero/reference/get-trips.md)
- [Pro API: access, limits and usage](https://docs.seats.aero/article/68-seatsaero-pro-api-access-limits-and-usage): daily allowance, reset time, remaining-calls header, endpoints open to Pro keys

The fallback ceilings (60,000 miles and 450 EUR in business, 35,000 miles and 200 EUR in economy) are starting assumptions, not sourced facts. The business figures come from published Miles & More price analyses by [meilenoptimieren](https://meilenoptimieren.com/?p=283425) and [reisetopia](https://reisetopia.de/deals/miles-more-award-deutschland-kuala-lumpur/amp/), and should be replaced by the tool's own route statistics after a few runs.

The chart rates are half the return prices between Europe and Southeast Asia in the [Miles & More award chart](https://www.miles-and-more.com/content/dam/mmg/touchpoint/web/pdf/Flight_Awards_DE.pdf), dated 3 March 2026: 85,000 miles in economy and 200,000 in business. That chart covers partner airlines; Lufthansa-group flights are priced dynamically.

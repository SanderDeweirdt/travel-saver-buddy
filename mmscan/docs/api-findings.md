# Live API findings (milestone 0)

Recorded by `mmscan check` on 2026-10-12 (4 calls, `X-RateLimit-Remaining`
999 → 996). Where the live response differs from the PRD's API section, the
live response wins, and the difference is listed here.

The raw responses are in `tests/fixtures/live/*.json` on the machine that ran
the check. They are git-ignored, not committed: this repository is public and
the seats.aero terms forbid redistributing the data.

## Answers to the milestone 0 questions

| Question | PRD expectation | Live answer |
| --- | --- | --- |
| Bulk Availability envelope | `data`, `count`, `hasMore`, `cursor` (undocumented) | Same as Cached Search: `data`, `count`, `hasMore`, `cursor`, plus `moreURL` (a ready-made next-page path with `skip` and `cursor`) |
| Tax fields on the summary (availability) object | none | **Present.** `{P}TotalTaxes` (int, minor units) per cabin, plus one `TaxesCurrency` per availability. It equals the taxes of that cabin's cheapest-miles trip in all 10 search results checked |
| Minified trips keep `TotalTaxes` | unknown | Yes. Minified trips keep `ID`, `AvailabilityID`, `Cabin`, `MileageCost`, `TotalTaxes`, `RemainingSeats`, `Stops`, `Carriers`, `TotalDuration`, and drop `TaxesCurrency`, `DepartsAt`, `ArrivesAt`, `FlightNumbers`, segments and the rest |
| `TaxesCurrency` value for `lufthansa` | may be empty | **`USD`** on every availability and trip (10 bulk, 10 search, 213 trips). Never empty, never EUR |
| Taxes per passenger | assumed per adult | Consistent with per adult (the Miles & More booking link carries `adults=1`; amounts such as 340 USD MUC-SIN economy fit one ticket). Not provable from the data alone |
| `TotalDuration` unit | looks like minutes | Minutes. ZRH 19:55 → BOM 23:50 next day is 1465; with ZRH at UTC+2 and BOM at UTC+5:30 that is 24 h 25 min. This also confirms times are airport local |
| Trip `Cabin` spelling | `economy` / `business` / `first` | Lower case already: `economy`, `business` |
| Per-cabin seat counts on `lufthansa` | present | Present but often 0: 9 of 20 summary business counts were 0 next to non-zero ones. Treating 0 as unknown stays right |
| `booking_links` on Get Trips | `label`, `link`, `primary` | As expected; the primary one is "Book via Miles & More", a prefilled award search link |

## Other differences from the PRD

- **`AvailabilityTrips` on Bulk Availability** is an empty list `[]`, not
  null.
- **Extra summary fields:** every per-cabin field has a `...Raw` twin
  (`JMileageCostRaw` is an int where `JMileageCost` is a string), and there
  are `{P}Direct...` variants (`JDirectMileageCost`, `JDirectTotalTaxes`,
  `JDirectRemainingSeats`, `JDirectAirlines`) for the cheapest nonstop.
- **`Route`** has `Connecting` and no `NumDaysOut`.
- **Trip objects** add `OriginAirport`, `DestinationAirport`, `Connections`,
  `Aircraft`, `FareClasses`, `TotalSegmentDistance`, `RouteID`, `CreatedAt`,
  `UpdatedAt`. `MixedCabinPct` did not appear.
- **Get Trips top level** adds `origin_coordinates`,
  `destination_coordinates` and `carriers`.
- **Dates start today:** a scan with no `start_date` returns flights departing
  today.
- **`UpdatedAt`** has microseconds (`2026-10-12T11:17:22.611864Z`).

## What this means for mmscan

1. **Blocking: fees are in USD.** Builder call 3 treats any non-EUR currency
   as unpriced, so as built every result is unpriced and the Shortlist is
   always empty. Fees need converting from USD to EUR.
2. **Region results come with fees.** The summary's `{P}TotalTaxes` gives the
   cash co-payment of the cheapest trip, so every region result can be priced
   without Get Trips. `enrich` would then only be needed for flight numbers,
   times and the booking link, or could be dropped from the default run.
3. Minor: an empty `AvailabilityTrips` list from a watchlist search should not
   be stored as a successful trip fetch with no trips.

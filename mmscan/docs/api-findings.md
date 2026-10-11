# Live API findings (milestone 0)

Filled in from `tests/fixtures/live/*.json`, recorded by `mmscan check`
(4 calls). Where the live response differs from the PRD's API section, the
live response wins, and the difference is listed here.

**Status: not yet recorded.** `SEATS_AERO_API_KEY` is not set, and
`seats.aero` is not reachable from the build environment.

| Question | PRD expectation | Live answer |
| --- | --- | --- |
| Bulk Availability envelope | `data`, `count`, `hasMore`, `cursor` (undocumented) | _pending_ |
| Tax fields on the summary (availability) object | none | _pending_ |
| Minified trips keep `TotalTaxes` | unknown | _pending_ |
| `TaxesCurrency` value for `lufthansa` | may be empty | _pending_ |
| Taxes per passenger | assumed per adult | _pending_ |
| `TotalDuration` unit | looks like minutes | _pending_ |
| Trip `Cabin` spelling | `economy` / `business` / `first` assumed | _pending_ |
| Per-cabin seat counts on `lufthansa` | present | _pending_ |
| `booking_links` on Get Trips | `label`, `link`, `primary` | _pending_ |

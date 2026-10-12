# mmscan design

The design is the PRD, unchanged: [`docs/PRD.md`](../../PRD.md). This file
records only where the project lives and the calls the builder made where
the PRD leaves a choice open. Every call below is the builder's, not
Sander's, and can be overruled.

## Where it lives

A self-contained `mmscan/` folder inside the `travel-saver-buddy` repo, with
its own `pyproject.toml`, `.gitignore`, tests and README. It shares no code
with the web app. All paths in the plan are relative to `mmscan/`.

## Builder calls

1. **Extra modules.** Besides config, client, store, scoring, enrich, report
   and cli: `models.py` (parsing API objects), `scan.py` (steps 1 and 2),
   `fares.py` (cash fare interface) and `diff.py` (new / cheaper).
2. **Unknown airports.** There is no airport database. An entry in
   `watchlist` or `subregions` that is not three uppercase letters is the
   "unknown airport" warning.
3. **Tax currency.** `TotalTaxes / 100` is used as euros when
   `TaxesCurrency` is `EUR` or empty. Empty is flagged in the run log. Any
   other currency makes that trip unpriced, with a warning. Milestone 0
   shows which case is real.
4. **Seats.** A trip whose seat count is unknown (0) counts as meeting
   `min_seats` when choosing a trip and for `seats_ok`. The report shows
   it as "unknown".
5. **Both layers good, too few seats.** The verdict is Worth a look, not
   Skip, because the PRD keeps such results "kept but flagged".
6. **Percentiles.** Thresholds use linear interpolation (numpy's default).
   The percentile shown in the report is a mid-rank:
   `(count below + 0.5 × count equal) / n × 100`.
7. **Baseline samples.** When the same route, date and cabin was seen in
   several runs inside `history_days`, only its latest observation counts.
8. **Fee estimate.** This is the median fee of priced results on the same
   route *and cabin*.
9. **Pre-screen.** A region result is a candidate when it is in the
   cheapest 30% of its route group *or* its destination group, in any
   configured cabin. Availabilities whose trips are already cached for
   their current `UpdatedAt` are not candidates.
10. **Fee spread (milestone 2).** `mmscan enrich` ends by printing min,
    median and max fee per route and cabin. The Route stats sheet repeats
    the median later.
11. **Previous run.** For New and Cheaper, this is the most recent earlier
    run that has scored results.
12. **Pagination guard.** A scan stops paging when a page adds no new `ID`,
    even if `hasMore` is still true, and warns.
13. **Fixtures before milestone 0.** Until live responses are recorded,
    unit tests use small hand-written fixtures in `tests/fixtures/synthetic/`,
    shaped exactly as the PRD's API section describes. Recorded responses
    go in `tests/fixtures/live/` and replace the synthetic ones wherever
    they differ.
14. **Fees in USD (milestone 0 finding).** `usd_to_eur` converts fees at a
    fixed rate from the config. USD without a rate is unpriced, with a run
    log warning. Empty currency is still read as EUR.
15. **Fees from the summary.** A region result is priced from the summary's
    `{P}TotalTaxes` when no trip details are stored; stored trips win. Zero
    or missing taxes mean unknown. `run` fetches trip details only for
    Shortlist results, after a first scoring pass.

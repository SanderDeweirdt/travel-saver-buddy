# mmscan

A command-line tool that pulls Miles & More award availability from the
seats.aero API, scores every result against configurable benchmarks, and
writes a ranked shortlist. The design is in [`docs/PRD.md`](docs/PRD.md).

> Cached data. Confirm price and seats on miles-and-more.com before acting.

Personal, non-commercial use only, as the seats.aero API terms require.

## Setup

```bash
cd mmscan
uv sync
cp .env.example .env   # then put your seats.aero Pro API key in it
```

## Status

Milestone 0 (access check) and the milestone 1 code (scan and store) are
built. The live gates have not run yet: `seats.aero` is not reachable from
the build environment, so the tests use the hand-written fixtures in
`tests/fixtures/synthetic/`.

```bash
uv run mmscan check --dry-run   # shows the 4 requests, sends nothing
uv run mmscan check             # 4 API calls; saves tests/fixtures/live/*.json
uv run mmscan scan --dry-run    # first request per region pair and watchlist direction
uv run mmscan scan              # region pairs and watchlist; pages as needed
uv run mmscan quota             # calls left today and calls made; 0 API calls
uv run pytest                   # offline tests
```

What the live API returned is recorded in
[`docs/api-findings.md`](docs/api-findings.md).

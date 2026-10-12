# Prompt: deploy mmscan on Railway with Postgres and a private dashboard

Paste everything below the line into a new Claude Code session on this repository.

---

You are working in `SanderDeweirdt/travel-saver-buddy`. Develop on branch `claude/dreamy-goldberg-rbociy` (create it from the default branch if it does not exist) and push there. Do not open a pull request unless I ask.

## Context

`mmscan/` is a Python 3.12 CLI (uv, typer, httpx, pydantic, openpyxl) that pulls Miles & More award availability from the seats.aero API, scores it, writes reports and posts Slack alerts. Read `mmscan/README.md`, `mmscan/docs/PRD.md`, `mmscan/src/mmscan/store.py` and `mmscan/src/mmscan/cli.py` first. The rest of the repo (React/Vite/Supabase, `src/`, `supabase/`) is an unrelated product: do not touch it.

Today all state lives in SQLite (`data/mmscan.db`, all access in `store.py`, about 370 lines). I want to host it on Railway with a private web dashboard. Agreed architecture, one Railway project with three pieces:

1. **Postgres** (Railway plugin) is the single source of truth, read through `DATABASE_URL`.
2. **Scanner**, a Railway cron service. It runs hourly and executes `mmscan watch` every time, plus `mmscan run` when the UTC hour is 05.
3. **Dashboard**, a Railway web service. Read-only view of the data, behind a login. For my private use only.

A Railway volume can mount on only one service, which is why Postgres replaces SQLite in production.

## Constraints

- Personal, non-commercial use. seats.aero terms forbid redistributing data: never commit real API responses, DB dumps or reports, and keep the dashboard private (login required on every route except the health check).
- Secrets only from environment variables: `SEATS_AERO_API_KEY`, `SLACK_WEBHOOK_URL`, `DATABASE_URL`, `DASHBOARD_PASSWORD`, `SESSION_SECRET`. Never put them in `config.yaml`, logs, fixtures, code or docs. Update `.env.example` with names only.
- Keep SQLite working for local use and for the existing test suite. Production selects Postgres when `DATABASE_URL` is set. The existing tests must keep passing unchanged where possible.
- Respect the existing daily call cap (`api.daily_call_cap`). It must still work across runs, so the call counting that reads `api_calls` must work on Postgres.
- Match the existing code style: ruff, line length 100, type hints, small modules.

## Work, in this order (commit after each step)

### 1. Postgres support in the store

- Add `psycopg[binary]` (v3) as a dependency.
- Make `store.py` backend-agnostic: same public methods, two backends. Prefer a thin adapter (placeholders, upsert syntax, `row_factory`, datetime handling, autoincrement vs `BIGSERIAL`/identity) over duplicating the 370 lines. Create the schema idempotently on startup for both backends.
- Check every SQL statement for SQLite-only features (`INSERT OR REPLACE`, `datetime('now')`, `rowid`, `PRAGMA`, type affinity, boolean and JSON storage) and port them properly.
- Add an index review: queries by run, route and date must be fast with 180 days of history.
- Tests: keep the SQLite tests. Add a parametrised fixture that runs the store tests against Postgres when `TEST_DATABASE_URL` is set and skips otherwise. If a local Postgres is available in the sandbox, run them for real and report the result. If not, say clearly that the Postgres path was not exercised.
- Add `mmscan migrate-sqlite --from data/mmscan.db` to copy existing SQLite data into Postgres (idempotent, prints counts). Skip it if there is no old data worth moving, but say so.

### 2. Railway packaging for the scanner

- `Dockerfile` (python 3.12-slim, uv, `uv sync --frozen --no-dev`). One image serves both services. The start command differs per service.
- `deploy/cron.sh`, started by Railway at `7 * * * *`. It runs `mmscan watch`, and also `mmscan run` when `date -u +%H` is `05`. It must exit non-zero when a command fails, still run the second command when the first fails, and exit promptly (Railway cron services must exit).
- Reports (`.xlsx`/`.csv`) must not depend on a persistent disk. Generate them on demand (see dashboard) and make the CLI write to a temp dir in the cron run.
- Railway config as code: `mmscan/railway.scanner.json` (cron schedule, start command, restart policy `NEVER` or `ON_FAILURE` as appropriate) and `mmscan/railway.web.json` (start command, healthcheck path `/healthz`). Use the current Railway config-as-code schema. Check the Railway docs rather than guessing field names.
- `config.yaml` is baked into the image. Document how to change it (commit and redeploy).

### 3. Dashboard

A small FastAPI app in `mmscan/src/mmscan/web/`, started with `mmscan web` (uvicorn, binds `0.0.0.0:$PORT`). It shares the package's models, scoring and store code with the scanner.

- **Auth**: one shared password (`DASHBOARD_PASSWORD`). Login page, signed session cookie (`SESSION_SECRET`, `HttpOnly`, `Secure` when behind https, `SameSite=Lax`), constant-time password comparison, basic rate limiting on failed logins, logout. Everything except `/healthz` and the login page requires a session. Refuse to start if either secret is missing.
- **Pages** (server-rendered Jinja2 plus a little htmx or vanilla JS, no build step, no heavy JS framework, responsive for phone):
  - Shortlist: latest scored run, filterable by route, cabin and verdict (Deal etc.), sortable. Show miles, fees, total cost, baseline and percentile, seats, flags and last-seen/New/Cheaper changes. Include the "cached data, confirm on miles-and-more.com" note.
  - Route detail: price history over time for one route and cabin, with a simple chart (inline SVG or a small CDN-free script).
  - Runs: run log with kind, status (`partial` highlighted), and calls used.
  - Quota: calls today against the daily cap, last `X-RateLimit-Remaining`.
  - Downloads: `GET /reports/latest.xlsx` and `/reports/latest-shortlist.csv`, built on demand from the DB using the existing report code.
- All DB access read-only. No endpoint may trigger a scan or spend API calls.
- Use the `dataviz` skill for the charts. Tests: use FastAPI `TestClient` for auth (anonymous requests are blocked, a wrong password fails, the right one works), the healthcheck, the Shortlist page against fixture data, and the report downloads.

### 4. Docs

- Update `mmscan/README.md` with a "Deploy on Railway" section and document every env var.
- Write step-by-step Railway instructions I can follow by hand, since the tools you have probably cannot create projects, databases or services: create the project, add the Postgres plugin, add two services from this repo using the right root directory and config file, set the variables and reference `DATABASE_URL` from the Postgres service, set the cron schedule, generate a domain for the web service, and run `mmscan migrate-sqlite` if relevant. Include a first-deploy verification checklist (healthcheck, login, a manual `mmscan check`, one `watch` run, the dashboard showing data).
- If Railway MCP tools are available in your session, you may use their read-only tools to verify config fields. Ask before changing anything on my Railway account.

## Done when

- `uv run pytest` and `uv run ruff check` pass in `mmscan/`.
- You can run the dashboard locally against SQLite with fixture data, and your final message states what you saw (a screenshot or described output of the login, Shortlist and route pages).
- Everything is pushed to `claude/dreamy-goldberg-rbociy`.
- Your final message covers what is verified and what is not (especially the Postgres path and anything Railway-specific you could not test), the exact manual steps left for me, and any risks such as cost, the call cap or the seats.aero terms.

Work autonomously. Ask me only for decisions that are genuinely mine (for example, if a Railway feature does not behave as assumed above).

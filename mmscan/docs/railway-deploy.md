# Deploy mmscan on Railway: step by step

One Railway project, three pieces: **Postgres**, a **scanner** cron service and a **dashboard**
web service. Both services build the same image from `mmscan/Dockerfile`.

> **Config as code is deprecated on Railway.** The docs say `railway.json` files keep working
> only for services that already use them until 2026-12-01, and that new services cannot opt in.
> `mmscan/railway.scanner.json` and `mmscan/railway.web.json` are in the repo and hold the exact
> settings, but treat them as a reference: **set the same values in each service's Settings**
> (below). If you want them enforced as code, Railway's replacement is Infrastructure as Code
> (`.railway/railway.ts`); that is not set up here.

## 1. Project and database

1. Railway dashboard, **New Project**, **Empty project**.
2. **Add**, **Database**, **PostgreSQL**. Railway creates a `Postgres` service with a
   `DATABASE_URL` variable. Nothing else to configure; no volume is needed for mmscan.

## 2. Scanner service (cron)

1. **Add**, **GitHub repo**, pick `SanderDeweirdt/travel-saver-buddy`. Name the service `scanner`.
2. Settings:
   - **Source, Root Directory**: `mmscan`
   - **Build, Builder**: Dockerfile (path `Dockerfile`; auto-detected)
   - **Deploy, Custom Start Command**: `sh deploy/cron.sh`
   - **Deploy, Cron Schedule**: `7 11 * * *` (UTC, daily at 11:07)
   - **Deploy, Restart Policy**: Never (a failed run must not retry and spend API calls)
3. Variables (Variables tab):
   - `DATABASE_URL` = `${{Postgres.DATABASE_URL}}` (reference variable, pick it from the dropdown)
   - `SEATS_AERO_API_KEY` = your key
   - `SLACK_WEBHOOK_URL` = your webhook. `notify.slack` is `true` in the shipped `config.yaml`, so
     without it every scan logs a "notify failed" warning and posts nothing (the scan itself still
     succeeds)

Each run does `mmscan run` (the full daily scan: all `region_pairs`, including Asia to Asia, plus
the watchlist). There is no hourly `mmscan watch`; `cron.sh` also checks the hour, so the full scan
runs only at 11 UTC even if the schedule is ever set to hourly.

## 3. Dashboard service (web)

1. **Add**, **GitHub repo**, same repo again. Name it `dashboard`.
2. Settings:
   - **Root Directory**: `mmscan`
   - **Deploy, Custom Start Command**: `mmscan web`
   - **Deploy, Healthcheck Path**: `/healthz`
   - **Networking, Generate Domain**
3. Variables:
   - `DATABASE_URL` = `${{Postgres.DATABASE_URL}}`
   - `DASHBOARD_PASSWORD` = a long password
   - `SESSION_SECRET` = random string, for example `openssl rand -hex 32`

The dashboard has no seats.aero key: it cannot call the API.

### Where it lives

The dashboard is at **https://travel-saver-buddy-production.up.railway.app** (the `dashboard` service's
Railway domain). Everything except `/healthz` asks for `DASHBOARD_PASSWORD`. Paths: `/` Best deals,
`/overview` All routes, `/trips`, `/shortlist` (old bookmarks with `?run=…&verdict=…&sort=verdict` belong
here, not on `/`), `/data` Data & alerts, `/route/<from>/<to>/<cabin>`, and `/healthz` (`ok`, no login).

Last checked 16 Oct 2026 from outside, without the password: `/healthz` returned 200 and `/shortlist` and
`/data` redirected to the login page, so the v2 build was running. Pages behind the login were not checked.

## 4. Move existing local data (optional)

If `data/mmscan.db` holds history you want (baselines need history), copy it once from your
machine, using the Postgres **public** connection string (Postgres service, Connect tab):

```bash
cd mmscan
DATABASE_URL='postgresql://…public url…' uv run mmscan migrate-sqlite --from data/mmscan.db
```

It prints rows copied per table and is safe to repeat. Skip it to start fresh.

## 4b. Recording price checks

The dashboard's "How far to trust cached miles" table is filled by hand. After comparing a result with
miles-and-more.com, record it with the Postgres **public** connection string:

```bash
cd mmscan
DATABASE_URL='postgresql://…public url…' uv run mmscan verify-add --carrier LH --cached 6000 --live 17000
```

The new `price_checks` table is created automatically the next time either service starts.

## 5. Changing `config.yaml`

`config.yaml` is baked into the image. Edit it, commit, push; Railway redeploys both services.
Secrets never go in it.

## First-deploy checklist

- [ ] Both services deployed green; Postgres is running.
- [ ] `https://<dashboard-domain>/healthz` returns `ok`.
- [ ] `/` redirects to the login page; the password logs you in; a wrong one is refused.
- [ ] Verify the key once: on the scanner service use **Run a command** or the Railway CLI
      (`railway run --service scanner mmscan check`). This makes 4 API calls.
- [ ] Trigger one scan: redeploy or wait for the `:07` run; the deploy logs end with
      `Watch ok: …`.
- [ ] Preview the Slack message: `railway run --service scanner mmscan notify --dry-run` (prints it,
      sends nothing). Without `--dry-run` it posts for real.
- [ ] The dashboard shows the run under **Runs** and rows on the **Shortlist** (a watch run only
      covers the watchlist; the daily 11 UTC run is the full picture).
- [ ] **Quota** shows calls today below the cap.
- [ ] **Data & alerts** shows the scanner as Healthy and the USD rate as checked within 30 days (`usd_to_eur_date`).

## Risks

- **Cost:** Railway bills by usage. The cron service runs for a few minutes a day; the
  dashboard and Postgres run all day. Check the usage page after a few days.
- **API cap:** `api.daily_call_cap` (300) is counted from the `api_calls` table, so it holds across
  runs. The daily `run` costs about 50 calls.
- **seats.aero terms:** personal, non-commercial use; do not redistribute data. The dashboard sits
  behind a login on every route except `/healthz`; keep the password private and do not share the
  downloads.

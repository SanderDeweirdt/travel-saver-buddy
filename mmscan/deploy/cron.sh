#!/bin/sh
# Railway cron entry point (schedule "7 11 * * *", UTC): the full daily scan, `mmscan run`.
# The hour check is a guard: if the schedule is ever set back to hourly, the full scan (about 50
# calls) still runs only once a day instead of eating the API quota.
# Railway cron services must exit, so the command is time-boxed. A full scan with Asia to Asia
# takes well over 40 minutes (about 265k results), so the box is two hours.

rc=0
report_dir="$(mktemp -d)"
export MMSCAN_REPORT_DIR="$report_dir"   # reports are built on demand by the dashboard instead

# Also scan on the first tick after every deployment: `deploy-pending` succeeds when no full run has
# started under this RAILWAY_DEPLOYMENT_ID yet. Needs the hourly schedule; a daily one waits for 11.
if [ "$(date -u +%H)" = "11" ] || mmscan deploy-pending; then
    timeout 120m mmscan run || rc=1
fi

# Postgres keeps the space of deleted rows inside its files, so the volume never shrinks by itself.
# Once a month, after the scan, rewrite the tables with `mmscan vacuum`.
if [ "$(date -u +%d)" = "01" ] && [ "$(date -u +%H)" = "11" ]; then
    timeout 20m mmscan vacuum || rc=1
fi

rm -rf "$report_dir"
exit "$rc"

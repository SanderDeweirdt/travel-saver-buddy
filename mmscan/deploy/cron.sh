#!/bin/sh
# Railway cron entry point (schedule "7 11 * * *", UTC): the full daily scan, `mmscan run`.
# The hour check is a guard: if the schedule is ever set back to hourly, the full scan (about 50
# calls) still runs only once a day instead of eating the API quota.
# Railway cron services must exit, so the command is time-boxed.

rc=0
report_dir="$(mktemp -d)"
export MMSCAN_REPORT_DIR="$report_dir"   # reports are built on demand by the dashboard instead

# FORCE_SCAN=1 (a Railway variable on the scanner service) runs the full scan on the next cron tick
# whatever the hour, e.g. right after a deploy. Remove the variable afterwards, or every tick scans.
if [ "$(date -u +%H)" = "11" ] || [ "${FORCE_SCAN:-}" = "1" ]; then
    timeout 40m mmscan run || rc=1
fi

# Postgres keeps the space of deleted rows inside its files, so the volume never shrinks by itself.
# Once a month, after the scan, rewrite the tables with `mmscan vacuum`.
if [ "$(date -u +%d)" = "01" ] && [ "$(date -u +%H)" = "11" ]; then
    timeout 20m mmscan vacuum || rc=1
fi

rm -rf "$report_dir"
exit "$rc"

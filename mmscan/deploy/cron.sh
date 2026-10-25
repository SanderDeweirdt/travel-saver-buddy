#!/bin/sh
# Railway cron entry point (schedule "7 11 * * *", UTC): the full daily scan, `mmscan run`.
# The hour check is a guard: if the schedule is ever set back to hourly, the full scan (about 50
# calls) still runs only once a day instead of eating the API quota.
# Railway cron services must exit, so the command is time-boxed.

rc=0
report_dir="$(mktemp -d)"
export MMSCAN_REPORT_DIR="$report_dir"   # reports are built on demand by the dashboard instead

if [ "$(date -u +%H)" = "11" ]; then
    timeout 40m mmscan run || rc=1
fi

rm -rf "$report_dir"
exit "$rc"

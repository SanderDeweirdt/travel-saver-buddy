#!/bin/sh
# Railway cron entry point (schedule "7 * * * *", UTC).
# Every run: `mmscan watch`. At 05 UTC also `mmscan run` (the full daily scan).
# A failing command does not stop the next one; the exit code is non-zero if any failed.
# Railway cron services must exit, so each command is time-boxed.

rc=0
report_dir="$(mktemp -d)"
export MMSCAN_REPORT_DIR="$report_dir"   # reports are built on demand by the dashboard instead

timeout 20m mmscan watch || rc=1

if [ "$(date -u +%H)" = "05" ]; then
    timeout 40m mmscan run || rc=1
fi

rm -rf "$report_dir"
exit "$rc"

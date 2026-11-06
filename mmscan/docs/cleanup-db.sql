-- Reclaim disk on the Railway Postgres volume. Run with psql against the PUBLIC connection string
-- (Postgres service, Connect tab), with the scanner not running (it runs daily at 11:07 UTC).
-- Order matters: measure, delete what is never read, null the raw copies, then rewrite the files.
-- psql runs each statement on its own, which VACUUM needs (it cannot run inside a transaction).

-- 1. Measure. Big n_dead_tup = rows were deleted but the file never shrank.
SELECT c.relname,
       pg_size_pretty(pg_total_relation_size(c.oid)) AS total,
       pg_size_pretty(pg_relation_size(c.oid))       AS heap,
       s.n_live_tup, s.n_dead_tup
FROM pg_class c
LEFT JOIN pg_stat_user_tables s ON s.relid = c.oid
WHERE c.relkind = 'r' AND c.relnamespace = 'public'::regnamespace
ORDER BY pg_total_relation_size(c.oid) DESC;

SELECT pg_size_pretty(pg_database_size(current_database())) AS database_size;

-- 2. Delete what the app no longer reads. Per-run copies: only the latest run is read.
--    TRUNCATE frees the disk immediately (no VACUUM needed) and needs no spare space, so it is
--    the safe first step when the volume is full. The next scan refills them for the latest run.
--    (If you would rather keep the latest run: use the DELETEs below instead of TRUNCATE.)
TRUNCATE availabilities, results;
-- DELETE FROM availabilities WHERE run_id < (SELECT max(id) FROM runs WHERE kind IN ('scan','run'));
-- DELETE FROM results        WHERE run_id < (SELECT max(id) FROM runs WHERE kind IN ('scan','run'));

-- 3. Trip details. trips/trip_fetches only matter for the latest run's availabilities, and the app
--    no longer stores their raw JSON. Keep 30 days, drop the raw copies of what is left.
DELETE FROM trips WHERE (availability_id, updated_at) IN
    (SELECT availability_id, updated_at FROM trip_fetches
     WHERE fetched_at < to_char(now() AT TIME ZONE 'utc' - interval '30 days', 'YYYY-MM-DD"T"HH24:MI:SS'));
DELETE FROM trip_fetches
    WHERE fetched_at < to_char(now() AT TIME ZONE 'utc' - interval '30 days', 'YYYY-MM-DD"T"HH24:MI:SS');
UPDATE trip_fetches SET raw_json = NULL WHERE raw_json IS NOT NULL;
UPDATE trips SET raw_json = '{}' WHERE raw_json <> '{}';

-- 4. Optional: old API call log and run configs (the full config is stored on every run).
DELETE FROM api_calls WHERE ts < to_char(now() AT TIME ZONE 'utc' - interval '90 days', 'YYYY-MM-DD"T"HH24:MI:SS');
UPDATE runs SET config_json = NULL
    WHERE started_at < to_char(now() AT TIME ZONE 'utc' - interval '14 days', 'YYYY-MM-DD"T"HH24:MI:SS');

-- 5. Give the space back to the volume. VACUUM FULL rewrites a table and needs free space about the
--    size of the table's live data, and locks it meanwhile. After step 2 there is room; go from the
--    biggest to the smallest, and re-run step 1 between tables if the volume is tight.
VACUUM (FULL, ANALYZE, VERBOSE) trip_fetches;
VACUUM (FULL, ANALYZE, VERBOSE) trips;
VACUUM (FULL, ANALYZE, VERBOSE) observations;
VACUUM (FULL, ANALYZE, VERBOSE) api_calls;
VACUUM (FULL, ANALYZE, VERBOSE) runs;
VACUUM (FULL, ANALYZE, VERBOSE) availabilities;
VACUUM (FULL, ANALYZE, VERBOSE) results;
VACUUM (FULL, ANALYZE, VERBOSE) current_offers;

-- 6. Check the result. Railway's usage graph can lag a few minutes.
SELECT pg_size_pretty(pg_database_size(current_database())) AS database_size;

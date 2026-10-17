"""Turn the per-run `results` history into `observations` (migration 3).

For each flight key, consecutive runs that saw the same price state collapse into one observation
covering first_seen..last_seen, which is what `offers.record_observations` would have written had it
been running all along. The raw fee currency was not kept in `results`, so `fees_minor` stays empty
and the converted `fees_eur` stands in; the first live scan adopts the real fee in place.
"""

from __future__ import annotations

from mmscan.store import Store

BATCH = 5000
COLUMNS = (
    "key, run_id, first_seen, last_seen, availability_id, origin, destination, origin_region, "
    "destination_region, date, cabin, miles, fees_eur, fee_estimated, expired, seats, stops, "
    "direct, carriers, flight_numbers, departs_at, arrives_at, booking_link, source_updated_at"
)


def _state(r) -> tuple:
    fees = None if r["fees_eur"] is None else round(r["fees_eur"], 2)
    return (r["miles"], fees, bool(r["fee_estimated"]), bool(r["expired"]))


def _observation(first, last) -> tuple:
    """`first` and `last` are the first and last results row of one unchanged price state."""
    key = f"{last['origin']}|{last['destination']}|{last['date']}|{last['cabin']}"
    return (
        key,
        first["run_id"],
        first["started_at"],
        last["started_at"],
        last["availability_id"],
        last["origin"],
        last["destination"],
        last["origin_region"],
        last["destination_region"],
        last["date"],
        last["cabin"],
        last["miles"],
        last["fees_eur"],
        int(bool(last["fee_estimated"])),
        int(bool(last["expired"])),
        last["seats"],
        last["stops"],
        last["direct"],
        last["carriers"],
        last["flight_numbers"],
        last["departs_at"],
        last["arrives_at"],
        last["booking_link"],
        last["updated_at"],
    )


def backfill_observations(store: Store) -> int:
    """Fill `observations` from `results`. Does nothing if observations already has rows. Returns
    the number of observations written."""
    if not store.postgres:
        store.conn.execute("BEGIN IMMEDIATE")  # take the write lock before looking, not after
    if store.conn.execute("SELECT 1 FROM observations LIMIT 1").fetchone():
        store.conn.rollback()
        return 0
    rows = store.conn.execute(
        "SELECT r.run_id, u.started_at, r.availability_id, r.origin, r.destination, "
        "r.origin_region, r.destination_region, r.date, r.cabin, r.miles, r.fees_eur, "
        "r.fee_estimated, r.expired, r.seats, r.stops, r.direct, r.carriers, r.flight_numbers, "
        "r.departs_at, r.arrives_at, r.booking_link, r.updated_at "
        "FROM results r JOIN runs u ON u.id = r.run_id "
        "WHERE r.miles IS NOT NULL AND r.date IS NOT NULL "
        "ORDER BY r.origin, r.destination, r.date, r.cabin, r.run_id"
    ).fetchall()
    marks = ",".join("?" * len(COLUMNS.split(",")))
    sql = f"INSERT INTO observations({COLUMNS}) VALUES ({marks})"
    batch: list[tuple] = []
    written = 0
    first = last = None
    group = None
    with store.conn:
        for r in rows:
            g = (r["origin"], r["destination"], r["date"], r["cabin"])
            if first is not None and g == group and _state(r) == _state(last):
                last = r
                continue
            if first is not None:
                batch.append(_observation(first, last))
            first = last = r
            group = g
            if len(batch) >= BATCH:
                store.conn.executemany(sql, batch)
                written += len(batch)
                batch = []
        if first is not None:
            batch.append(_observation(first, last))
        if batch:
            store.conn.executemany(sql, batch)
            written += len(batch)
    return written

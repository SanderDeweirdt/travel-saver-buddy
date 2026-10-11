from mmscan.enrich import select_candidates
from mmscan.scoring import percentile, percentile_rank
from mmscan.store import Store
from tests.helpers import avail, config, trip


def test_percentile_linear():
    assert percentile([1, 2, 3, 4], 50) == 2.5
    assert percentile([], 20) is None
    assert percentile([7], 20) == 7


def test_percentile_rank_mid():
    assert percentile_rank([1, 2, 3], 2) == 50.0
    assert percentile_rank([], 2) is None


def _store_with(tmp_path, avails):
    store = Store(tmp_path / "db.sqlite")
    run = store.start_run("scan", "{}")
    for a in avails:
        store.save_availability(run, a, "region")
    return store, run


def test_thirty_percent_cut_cheapest_first(tmp_path, default_config_dict):
    # Ten dates on one route, 10k to 100k: the 30% cut is 37k, so 10k, 20k and 30k stay.
    avails = [
        avail(f"a{i:02d}", date=f"2026-12-{i + 1:02d}", business=(10 - i) * 10000)
        for i in range(10)
    ]
    store, run = _store_with(tmp_path, avails)
    cfg = config(default_config_dict, cabins=["business"])
    assert select_candidates(store, cfg, run) == ["a09", "a08", "a07"]


def test_either_group_is_enough(tmp_path, default_config_dict):
    # FRA-SIN has one sample, so its route group always keeps it.
    avails = [
        avail(f"m{i}", date=f"2026-12-{i + 1:02d}", business=10000 * (i + 1)) for i in range(5)
    ]
    avails.append(avail("f1", origin="FRA", business=90000))
    store, run = _store_with(tmp_path, avails)
    cfg = config(default_config_dict, cabins=["business"])
    assert "f1" in select_candidates(store, cfg, run)


def test_cached_availability_excluded(tmp_path, default_config_dict):
    store, run = _store_with(
        tmp_path, [avail("a", business=50000), avail("b", origin="FRA", business=60000)]
    )
    store.save_trips("a", "2026-10-10T08:00:00Z", [trip("t1")], None, {})
    cfg = config(default_config_dict, cabins=["business"])
    assert select_candidates(store, cfg, run) == ["b"]

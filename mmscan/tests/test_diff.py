import json
from datetime import UTC, datetime

from typer.testing import CliRunner

from mmscan.cli import app
from mmscan.diff import change
from mmscan.scoring import score_run
from mmscan.store import Store
from tests.helpers import avail, config, trip

NOW = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)


def test_change_rules():
    assert change(None, 500) == "New"
    assert change(1000, 950) == "Cheaper"
    assert change(1000, 951) == ""
    assert change(1000, 1100) == ""


def _scan(store, run, taxes_by_id):
    for i, (avail_id, taxes) in enumerate(taxes_by_id.items()):
        updated = f"2026-10-1{run}T08:00:00Z"
        store.save_availability(
            run,
            avail(avail_id, date=f"2026-12-{i + 1:02d}", updated=updated, business=60000),
            "region",
        )
        store.save_trips(
            avail_id, updated, [trip(f"t{avail_id}{run}", avail_id=avail_id, taxes=taxes)], None, {}
        )


def test_two_scored_runs_fill_change(tmp_path, default_config_dict):
    cfg = config(default_config_dict, cabins=["business"])
    store = Store(tmp_path / "db.sqlite")
    r1 = store.start_run("scan", "{}", now=NOW)
    _scan(store, r1, {"a": 40000, "b": 40000})
    first, _ = score_run(store, cfg, r1, NOW)
    assert all(s.change == "" for s in first)  # nothing to compare with yet

    r2 = store.start_run("scan", "{}", now=NOW)
    _scan(store, r2, {"a": 40000, "b": 1000, "c": 40000})
    second, _ = score_run(store, cfg, r2, NOW)
    by_id = {s.availability_id: s.change for s in second}
    # b: 696 + 400 = 1096 before, 696 + 10 = 706 now.
    assert by_id == {"a": "", "b": "Cheaper", "c": "New"}


def test_run_dry_run_makes_no_calls(tmp_path, monkeypatch, default_config_dict):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text(json.dumps(default_config_dict))
    result = CliRunner().invoke(app, ["run", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "Planned calls: 4 scan requests" in result.output
    assert "GET /availability" in result.output and "GET /search" in result.output
    assert not (tmp_path / "data").exists()

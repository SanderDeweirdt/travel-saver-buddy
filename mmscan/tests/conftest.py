import os
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def default_config_dict() -> dict:
    data = yaml.safe_load((ROOT / "config.yaml").read_text())
    # The scan tests count requests for the two long-haul pairs; Asia to Asia has its own test.
    data["region_pairs"] = [p for p in data["region_pairs"] if p["origin"] != p["destination"]]
    data["notify"] = {"new_deals": {"enabled": False}}  # notify tests start from the code defaults
    return data


@pytest.fixture
def write_config(tmp_path):
    def _write(data: dict) -> Path:
        p = tmp_path / "config.yaml"
        p.write_text(yaml.safe_dump(data))
        return p

    return _write


TABLES = (
    "observations",
    "current_offers",
    "schema_version",
    "results",
    "trips",
    "trip_fetches",
    "availabilities",
    "api_calls",
    "runs",
    "price_checks",
)


@pytest.fixture(params=["sqlite", "postgres"])
def backend_store(request, tmp_path):
    """A Store on each backend. Postgres runs only when TEST_DATABASE_URL is set; the tables of
    that database are dropped before and after every test, so point it at a scratch database."""
    from mmscan.store import Store

    if request.param == "sqlite":
        store = Store(tmp_path / "db.sqlite")
        yield store
        store.close()
        return
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not set; the Postgres path is not exercised")
    for _ in range(2):
        store = Store(url)
        for table in TABLES:
            store.conn.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
        store.conn.commit()
        store.close()
    store = Store(url)  # fresh schema
    yield store
    store.close()

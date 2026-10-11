from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def default_config_dict() -> dict:
    return yaml.safe_load((ROOT / "config.yaml").read_text())


@pytest.fixture
def write_config(tmp_path):
    def _write(data: dict) -> Path:
        p = tmp_path / "config.yaml"
        p.write_text(yaml.safe_dump(data))
        return p

    return _write

"""Dashboard settings, read from the environment. Secrets never come from config.yaml."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class SettingsError(RuntimeError):
    pass


@dataclass(frozen=True)
class WebSettings:
    password: str
    secret: str
    database: Path | str
    config_path: Path
    secure_cookies: bool = True


def settings_from_env() -> WebSettings:
    missing = [k for k in ("DASHBOARD_PASSWORD", "SESSION_SECRET") if not os.environ.get(k)]
    if missing:
        raise SettingsError(f"Refusing to start: {', '.join(missing)} not set.")
    database = os.environ.get("DATABASE_URL") or Path("data/mmscan.db")
    return WebSettings(
        password=os.environ["DASHBOARD_PASSWORD"],
        secret=os.environ["SESSION_SECRET"],
        database=database,
        config_path=Path(os.environ.get("MMSCAN_CONFIG", "config.yaml")),
        secure_cookies=os.environ.get("DASHBOARD_INSECURE_COOKIES") != "1",
    )

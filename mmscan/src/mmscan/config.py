"""Load and validate config.yaml."""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

Region = Literal["North America", "South America", "Africa", "Asia", "Europe", "Oceania"]
Cabin = Literal["economy", "premium", "business", "first"]
REGIONS: tuple[str, ...] = Region.__args__  # type: ignore[attr-defined]
_IATA = re.compile(r"^[A-Z]{3}$")


class ConfigError(Exception):
    pass


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DateWindow(_Model):
    start_offset_days: int = Field(0, ge=0)
    end_offset_days: int = Field(330, ge=0)

    @model_validator(mode="after")
    def _ordered(self) -> DateWindow:
        if self.start_offset_days > self.end_offset_days:
            raise ValueError("start_offset_days must not exceed end_offset_days")
        return self


class RegionPair(_Model):
    origin: Region
    destination: Region


class Watchlist(_Model):
    origins: list[str] = []
    destinations: list[str] = []
    both_directions: bool = True


class Benchmark(_Model):
    name: str
    cabin: Cabin
    between: tuple[str, str]
    good_miles_max: int = Field(gt=0)
    chart_rate_miles: int = Field(gt=0)
    fees_max_eur: float = Field(ge=0)


class Relative(_Model):
    percentile_good: float = Field(20, gt=0, le=100)
    min_samples: int = Field(15, ge=1)
    history_days: int = Field(30, ge=0)


class Prescreen(_Model):
    percentile: float = Field(30, gt=0, le=100)


class Enrich(_Model):
    max_calls: int = Field(150, ge=0)


class ValueBands(_Model):
    good: float = 2.0
    fair: float = 1.5
    poor: float = 1.2


class Api(_Model):
    take: int = Field(1000, ge=10, le=1000)
    min_cabin_pct: int = Field(100, ge=0, le=100)
    include_filtered: bool = False
    daily_call_cap: int = Field(300, ge=1)


class Watch(_Model):
    max_pages: int = Field(1, ge=1)


class Notify(_Model):
    slack: bool = False
    verdicts: list[Literal["Deal", "Worth a look"]] = ["Deal"]
    changes: list[Literal["New", "Cheaper"]] = ["New", "Cheaper"]
    max_items: int = Field(10, ge=1, le=40)


class Output(_Model):
    dir: Path = Path("./reports")
    formats: list[Literal["xlsx", "csv"]] = ["xlsx", "csv"]


class Config(_Model):
    source: str = "lufthansa"
    cabins: list[Cabin] = Field(min_length=1)
    min_seats: int = Field(2, ge=1)
    mile_cost_eur_cents: float = Field(gt=0)
    usd_to_eur: float | None = Field(None, gt=0)
    date_window: DateWindow = DateWindow()
    region_pairs: list[RegionPair] = []
    watchlist: Watchlist = Watchlist()
    subregions: dict[str, list[str]] = {}
    benchmarks: list[Benchmark] = []
    relative: Relative = Relative()
    prescreen: Prescreen = Prescreen()
    enrich: Enrich = Enrich()
    value_per_mile_cents: ValueBands = ValueBands()
    api: Api = Api()
    output: Output = Output()
    notify: Notify = Notify()
    watch: Watch = Watch()

    warnings: list[str] = Field(default_factory=list, exclude=True)

    @model_validator(mode="after")
    def _check_places(self) -> Config:
        known = set(REGIONS) | set(self.subregions)
        for i, b in enumerate(self.benchmarks):
            for place in b.between:
                if place not in known:
                    raise ValueError(
                        f"benchmarks.{i}.between: {place!r} is neither an API region "
                        f"nor a subregion key"
                    )
        return self

    def date_range(self, today: date) -> tuple[date, date]:
        return (
            today + timedelta(days=self.date_window.start_offset_days),
            today + timedelta(days=self.date_window.end_offset_days),
        )

    def place_contains(self, place: str, airport: str, region: str) -> bool:
        if place == region:
            return True
        return airport in self.subregions.get(place, [])

    def benchmark_for(
        self, cabin: str, origin: str, origin_region: str, dest: str, dest_region: str
    ) -> Benchmark | None:
        for b in self.benchmarks:
            if b.cabin != cabin:
                continue
            a, z = b.between
            forward = self.place_contains(a, origin, origin_region) and self.place_contains(
                z, dest, dest_region
            )
            backward = self.place_contains(z, origin, origin_region) and self.place_contains(
                a, dest, dest_region
            )
            if forward or backward:
                return b
        return None


def _format_errors(err: ValidationError) -> str:
    lines = []
    for e in err.errors():
        loc = ".".join(str(p) for p in e["loc"]) or "(top level)"
        lines.append(f"{loc}: {e['msg']}")
    return "Invalid config:\n  " + "\n  ".join(lines)


def _airport_warnings(cfg: Config) -> list[str]:
    out = []
    lists = {
        "watchlist.origins": cfg.watchlist.origins,
        "watchlist.destinations": cfg.watchlist.destinations,
    }
    lists.update({f"subregions.{k}": v for k, v in cfg.subregions.items()})
    for where, codes in lists.items():
        for code in codes:
            if not _IATA.match(code):
                out.append(f"{where}: {code!r} does not look like an airport code")
    return out


def load_config(path: Path) -> Config:
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"Config file {path} is not valid YAML: {e}") from e
    if not isinstance(data, dict):
        raise ConfigError(f"Config file {path} must be a mapping at the top level")
    try:
        cfg = Config.model_validate(data)
    except ValidationError as e:
        raise ConfigError(_format_errors(e)) from e
    cfg.warnings.extend(_airport_warnings(cfg))
    return cfg

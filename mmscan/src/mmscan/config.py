"""Load and validate config.yaml."""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path
from string import Formatter
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

Region = Literal["North America", "South America", "Africa", "Asia", "Europe", "Oceania"]
Cabin = Literal["economy", "premium", "business", "first"]
# The mileage programs seats.aero lists as a `source` (developers.seats.aero, Concepts). A program
# outside this list is a typo, not a program, so config loading rejects it.
SOURCES = frozenset(
    "eurobonus virginatlantic aeromexico american delta etihad united emirates aeroplan alaska "
    "velocity qantas connectmiles azul flyingblue jetblue qatar turkish singapore ethiopian "
    "saudia finnair lufthansa frontier spirit".split()
)
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


class DateRange(_Model):
    start: date
    end: date

    @model_validator(mode="after")
    def _ordered(self) -> DateRange:
        if self.start > self.end:
            raise ValueError("start must not be after end")
        return self


class StayDays(_Model):
    min: int = Field(0, ge=0)
    max: int = Field(365, ge=0)

    @model_validator(mode="after")
    def _ordered(self) -> StayDays:
        if self.min > self.max:
            raise ValueError("min must not exceed max")
        return self


class TripProfile(_Model):
    """A trip you actually want to take. Scanned, paired and alerted on its own."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str = Field(min_length=1)
    origins: list[str] = Field(min_length=1)
    destinations: list[str] = Field(min_length=1)
    depart: DateRange
    # Leave out for a one-way trip.
    return_window: DateRange | None = Field(None, alias="return")
    stay_days: StayDays | None = None
    cabins: list[Cabin] | None = None  # default: the top-level cabins
    seats: int | None = Field(None, ge=1)  # default: the top-level min_seats
    max_stops: int | None = Field(None, ge=0)
    # Ceiling for the whole trip and all travellers, miles valued at mile_cost_eur_cents.
    max_total_eur: float | None = Field(None, gt=0)
    # Return from a different airport than you flew into (and back to a different origin).
    open_jaw: bool = False
    alert_top: int = Field(3, ge=1, le=20)

    @model_validator(mode="after")
    def _consistent(self) -> TripProfile:
        if self.return_window:
            if self.return_window.end < self.depart.start:
                raise ValueError("return window ends before the trip departs")
        elif self.stay_days:
            raise ValueError("stay_days needs a return window")
        return self

    @property
    def round_trip(self) -> bool:
        return self.return_window is not None


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
    # A route/destination layer is only "good" when the total is also at least this far below
    # the layer's median. 0 turns the rule off (the PRD's plain percentile cut).
    min_discount_pct: float = Field(10, ge=0, lt=100)


class ShortlistScope(_Model):
    # focus: only results matching a benchmark or the watchlist reach the Shortlist, the CSV
    # and Slack alerts. all: every Deal and Worth a look, as the PRD says.
    scope: Literal["focus", "all"] = "focus"
    focus_watchlist: bool = True


class Prescreen(_Model):
    percentile: float = Field(30, gt=0, le=100)


class Enrich(_Model):
    max_calls: int = Field(150, ge=0)


class ValueBands(_Model):
    good: float = 2.0
    fair: float = 1.5
    poor: float = 1.2


class Savings(_Model):
    # Verdict on the deals page: how far below the route's usual price (median total) a result is.
    great_pct: float = Field(30, gt=0, lt=100)
    good_pct: float = Field(10, gt=0, lt=100)

    @model_validator(mode="after")
    def _ordered(self):
        if self.good_pct >= self.great_pct:
            raise ValueError("good_pct must be below great_pct")
        return self


class Api(_Model):
    take: int = Field(1000, ge=10, le=1000)
    min_cabin_pct: int = Field(100, ge=0, le=100)
    include_filtered: bool = False
    daily_call_cap: int = Field(300, ge=1)


class Watch(_Model):
    max_pages: int = Field(1, ge=1)


class Deals(_Model):
    # Fixed-chart carriers only: miles at or under the matching benchmark's chart saver level,
    # with fees inside fees_max_eur, is a Deal (seats permitting). Dynamic carriers have no chart
    # and are only ever judged against the prices this tool has observed.
    by_ceiling: bool = True
    min_saving_pct: float = Field(30, ge=0)  # Best deals shows only savings this far below usual
    default_cabin: str = "economy"  # Best deals page filter when none is chosen; "" = all cabins


class Drops(_Model):
    # Change shows "Cheaper" when a total fell at least this % since it was last seen.
    min_pct: float = Field(5, gt=0, lt=100)


class NewDeals(_Model):
    """Alert on each flight (route, date and cabin) seen for the first time that is already at
    least `min_pct` below its route's usual price, on every route (not the shortlist focus)."""

    enabled: bool = True
    min_pct: float = Field(10, ge=0, le=100)
    cabins: list[str] = ["economy"]
    unverified: bool = True  # include dynamic-carrier prices, marked as such in the message


class Notify(_Model):
    slack: bool = False
    new_deals: NewDeals = NewDeals()
    # Also alert on Cheaper results of any verdict (inside the shortlist scope).
    on_drop: bool = True
    verdicts: list[Literal["Deal", "Worth a look"]] = ["Deal"]
    changes: list[Literal["New", "Cheaper"]] = ["New", "Cheaper"]
    # Alert on dynamic-carrier prices too. Off: their cached miles can be far below the live price.
    unverified: bool = False
    max_items: int = Field(10, ge=1, le=40)


class Storage(_Model):
    # Size of the Railway volume the database lives on, in GB. The app cannot see the volume, so
    # set it to the plan's size. The Data page and Slack warn when the database passes warn_pct.
    limit_gb: float = Field(5.0, gt=0)
    warn_pct: int = Field(70, ge=1, le=100)


class Output(_Model):
    dir: Path = Path("./reports")
    formats: list[Literal["xlsx", "csv"]] = ["xlsx", "csv"]


LINK_PLACEHOLDERS = {"origin", "destination", "date", "date_us", "cabin", "cabin_code", "adults"}


def template_fields(template: str) -> set[str]:
    return {name for _, name, _, _ in Formatter().parse(template) if name}


class MilesAndMore(_Model):
    # URL of a prefilled Miles & More award search. Placeholders: {origin}, {destination},
    # {date} (YYYY-MM-DD), {date_us} (MM/dd/yyyy), {cabin} (economy, business), {cabin_code}
    # (E, B, F: Miles & More's bookingclass) and {adults}. Empty = only stored links.
    link_template: str = ""

    @model_validator(mode="after")
    def _check_template(self) -> MilesAndMore:
        bad = template_fields(self.link_template) - LINK_PLACEHOLDERS
        if bad:
            raise ValueError(
                f"link_template: unknown placeholder {sorted(bad)}; use {sorted(LINK_PLACEHOLDERS)}"
            )
        return self


class Program(_Model):
    """One seats.aero mileage program (a `source`) with its own value per mile and booking link."""

    # What one mile of this program costs you, in euro cents. Unset = the top-level value.
    mile_cost_eur_cents: float | None = Field(None, gt=0)
    # Amex Membership Rewards points that buy one mile of this program (3 points = 2 miles is 1.5).
    # Set, it replaces mile_cost_eur_cents: a mile costs mr_per_mile x `mr_point_value_eur_cents`.
    mr_per_mile: float | None = Field(None, gt=0)
    # Prefilled award-search URL, same placeholders as miles_and_more.link_template.
    link_template: str = ""
    label: str = ""  # short name on the Book button; empty = the source id
    # Can you book with this program? Off = never requested from seats.aero and never shown.
    enabled: bool = True
    # Also scan flights within one region (Asia to Asia). Miles & More returns nothing there, so
    # only the partner programs that do are asked.
    within_region: bool = False

    @model_validator(mode="after")
    def _check_template(self) -> Program:
        bad = template_fields(self.link_template) - LINK_PLACEHOLDERS
        if bad:
            raise ValueError(
                f"link_template: unknown placeholder {sorted(bad)}; use {sorted(LINK_PLACEHOLDERS)}"
            )
        return self


class Config(_Model):
    source: str = "lufthansa"
    # The one list of mileage programs, keyed by seats.aero source id: what each costs you, whether
    # you can book it (`enabled`) and where it is scanned. The top-level `source` (Miles & More) is
    # always on and falls back to mile_cost_eur_cents and miles_and_more.link_template.
    programs: dict[str, Program] = {}
    # What one Amex Membership Rewards point is worth to you, in euro cents. Turns points sent to a
    # transfer partner into euros, so those awards compare with Miles & More on one total.
    mr_point_value_eur_cents: float | None = Field(None, gt=0)
    # IATA codes of Miles & More carriers that price awards dynamically (no chart). Everything
    # else on the program is a fixed partner chart. The list has grown before: keep it current.
    dynamic_airlines: list[str] = ["LH", "LX", "OS", "CL", "4Y", "EN", "WK"]
    cabins: list[Cabin] = Field(min_length=1)
    min_seats: int = Field(2, ge=1)
    mile_cost_eur_cents: float = Field(gt=0)
    usd_to_eur: float | None = Field(None, gt=0)
    usd_to_eur_date: date | None = None  # when the rate above was last checked
    date_window: DateWindow = DateWindow()
    region_pairs: list[RegionPair] = []
    watchlist: Watchlist = Watchlist()
    subregions: dict[str, list[str]] = {}
    benchmarks: list[Benchmark] = []
    relative: Relative = Relative()
    prescreen: Prescreen = Prescreen()
    enrich: Enrich = Enrich()
    value_per_mile_cents: ValueBands = ValueBands()
    savings: Savings = Savings()
    api: Api = Api()
    output: Output = Output()
    notify: Notify = Notify()
    storage: Storage = Storage()
    shortlist: ShortlistScope = ShortlistScope()
    deals: Deals = Deals()
    miles_and_more: MilesAndMore = MilesAndMore()
    drops: Drops = Drops()
    watch: Watch = Watch()
    trips: list[TripProfile] = []
    # Trip results older than this (by run start) are ignored when pairing legs.
    trip_freshness_hours: int = Field(72, ge=1)

    warnings: list[str] = Field(default_factory=list, exclude=True)

    @model_validator(mode="after")
    def _check_sources(self) -> Config:
        unknown = sorted(({self.source} | set(self.programs)) - SOURCES)
        if unknown:
            raise ValueError(
                f"unknown seats.aero source(s) {unknown}; valid sources: {sorted(SOURCES)}"
            )
        return self

    @model_validator(mode="after")
    def _check_amex(self) -> Config:
        needs = sorted(k for k, p in self.programs.items() if p.mr_per_mile)
        if needs and self.mr_point_value_eur_cents is None:
            raise ValueError(
                f"programs {needs} use mr_per_mile, so mr_point_value_eur_cents must be set"
            )
        return self

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
        names = [t.name for t in self.trips]
        if len(set(names)) != len(names):
            raise ValueError("trips: names must be unique")
        return self

    def is_bookable(self, source: str | None) -> bool:
        """Can you book this program's awards? The default program always; others when enabled.
        A flight with no stored source is the default one."""
        key = source or self.source
        program = self.programs.get(key)
        return key == self.source or bool(program and program.enabled)

    def sources_for(self, pair: RegionPair) -> list[str]:
        """The programs to ask for one region pair, from `programs` alone. Between two regions:
        Miles & More and every enabled program. Within one region: enabled `within_region` ones."""
        enabled = [k for k, p in self.programs.items() if p.enabled and k != self.source]
        if pair.origin == pair.destination:
            return [k for k in enabled if self.programs[k].within_region]
        return [self.source, *enabled]

    def mile_cents(self, source: str | None) -> float:
        """Euro cents one mile of `source` costs you. No source means the default program."""
        program = self.programs.get(source or self.source)
        if program and program.mr_per_mile and self.mr_point_value_eur_cents:
            return program.mr_per_mile * self.mr_point_value_eur_cents
        return (program.mile_cost_eur_cents if program else None) or self.mile_cost_eur_cents

    def link_template_for(self, source: str | None) -> str:
        program = self.programs.get(source or self.source)
        if program and program.link_template:
            return program.link_template
        return self.miles_and_more.link_template if (source or self.source) == self.source else ""

    def program_label(self, source: str | None) -> str:
        key = source or self.source
        program = self.programs.get(key)
        if program and program.label:
            return program.label
        return "M&M" if key == "lufthansa" else key

    def trip_cabins(self, trip: TripProfile) -> list[str]:
        return list(trip.cabins or self.cabins)

    def trip_seats(self, trip: TripProfile) -> int:
        return trip.seats or self.min_seats

    def focus_reasons(
        self, origin: str, origin_region: str, dest: str, dest_region: str, cabin: str
    ) -> list[str]:
        """Why a flight is on the Watchlist page: "watchlist" when its airports are a watchlist
        pair (and shortlist.focus_watchlist is on), "benchmark" when it matches a benchmark."""
        out = []
        wl = self.watchlist
        if self.shortlist.focus_watchlist and (
            (origin in wl.origins and dest in wl.destinations)
            or (wl.both_directions and origin in wl.destinations and dest in wl.origins)
        ):
            out.append("watchlist")
        if self.benchmark_for(cabin, origin, origin_region, dest, dest_region):
            out.append("benchmark")
        return out

    def in_focus(
        self, origin: str, origin_region: str, dest: str, dest_region: str, cabin: str
    ) -> bool:
        """Matches a benchmark, or (when focus_watchlist) a watchlist airport pair."""
        return bool(self.focus_reasons(origin, origin_region, dest, dest_region, cabin))

    def date_range(self, today: date) -> tuple[date, date]:
        return (
            today + timedelta(days=self.date_window.start_offset_days),
            today + timedelta(days=self.date_window.end_offset_days),
        )

    def place_contains(self, place: str, airport: str, region: str) -> bool:
        if place == region:
            return True
        return airport in self.subregions.get(place, [])

    def usd_rate_age_days(self, today: date) -> int | None:
        return None if self.usd_to_eur_date is None else (today - self.usd_to_eur_date).days

    def pricing_model(self, carriers: str | None) -> str:
        """ "fixed" when no carrier on the result prices dynamically, "dynamic" when all do, and
        "mixed" when both or none are known. Mixed is judged like dynamic: the long-haul operator
        decides in reality, and the stored result does not say which that is."""
        codes = {c.strip().upper() for c in (carriers or "").split(",") if c.strip()}
        if not codes:
            return "mixed"
        dynamic = {c.upper() for c in self.dynamic_airlines}
        if codes <= dynamic:
            return "dynamic"
        if codes.isdisjoint(dynamic):
            return "fixed"
        return "mixed"

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
    for t in cfg.trips:
        lists[f"trips.{t.name}.origins"] = t.origins
        lists[f"trips.{t.name}.destinations"] = t.destinations
    for where, codes in lists.items():
        for code in codes:
            if not _IATA.match(code):
                out.append(f"{where}: {code!r} does not look like an airport code")
    return out


# What the dashboard's Settings page may change. Everything else stays in config.yaml.
SETTING_KEYS = ("mr_point_value_eur_cents", "mile_cost_eur_cents")


def apply_overrides(data: dict, overrides: dict | None) -> dict:
    """config.yaml's mapping with the saved settings on top. `programs` merges per program and per
    field, so a saved value never drops a program's link template or label."""
    if not overrides:
        return data
    merged = dict(data)
    for key in SETTING_KEYS:
        if key in overrides:
            merged[key] = overrides[key]
    saved = overrides.get("programs")
    legacy = overrides.get("bookable_programs")  # saved before `enabled` moved into each program
    if isinstance(saved, dict) or isinstance(legacy, list):
        programs = {k: dict(v or {}) for k, v in (data.get("programs") or {}).items()}
        if isinstance(legacy, list):
            for name, fields in programs.items():
                fields["enabled"] = name in legacy
        for name, fields in (saved or {}).items():
            programs[name] = {**programs.get(name, {}), **(fields or {})}
        merged["programs"] = programs
    return merged


def load_config(path: Path, overrides: dict | None = None) -> Config:
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
        cfg = Config.model_validate(apply_overrides(data, overrides))
    except ValidationError as e:
        raise ConfigError(_format_errors(e)) from e
    cfg.warnings.extend(_airport_warnings(cfg))
    return cfg

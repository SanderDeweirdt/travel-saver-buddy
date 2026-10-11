"""Cash fares: a small interface so an automatic source can replace the CSV later."""

from __future__ import annotations

import csv
import logging
import re
from pathlib import Path
from typing import Protocol

from mmscan.config import Config

log = logging.getLogger("mmscan.fares")
_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
COLUMNS = ("origin", "destination", "cabin", "month", "fare_eur")


class FareSource(Protocol):
    def fare(self, origin: str, destination: str, cabin: str, month: str) -> float | None: ...


class NoFares:
    warnings: list[str] = []

    def fare(self, origin: str, destination: str, cabin: str, month: str) -> float | None:
        return None


class CsvFareSource:
    """Reads `cash_fares.csv`. A missing file means no fares; bad rows are skipped."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.warnings: list[str] = []
        self._fares: dict[tuple[str, str, str, str], float] = {}
        if self.path.exists():
            self._load()

    def _warn(self, msg: str) -> None:
        log.warning(msg)
        self.warnings.append(msg)

    def _load(self) -> None:
        with self.path.open(newline="") as f:
            reader = csv.DictReader(f)
            missing = [c for c in COLUMNS if c not in (reader.fieldnames or [])]
            if missing:
                self._warn(f"{self.path}: missing columns {', '.join(missing)}; no fares read")
                return
            for row in reader:
                line = reader.line_num
                month = (row["month"] or "").strip()
                if not _MONTH.match(month):
                    self._warn(f"{self.path} line {line}: month {month!r} is not YYYY-MM; skipped")
                    continue
                try:
                    fare = float((row["fare_eur"] or "").strip())
                except ValueError:
                    self._warn(
                        f"{self.path} line {line}: fare_eur {row['fare_eur']!r} is not a number; "
                        f"skipped"
                    )
                    continue
                key = (
                    row["origin"].strip().upper(),
                    row["destination"].strip().upper(),
                    row["cabin"].strip().lower(),
                    month,
                )
                self._fares[key] = fare

    def fare(self, origin: str, destination: str, cabin: str, month: str) -> float | None:
        return self._fares.get((origin, destination, cabin, month))


def value_band(cents: float | None, cfg: Config) -> str | None:
    if cents is None:
        return None
    bands = cfg.value_per_mile_cents
    if cents >= bands.good:
        return "good"
    if cents >= bands.fair:
        return "fair"
    return "poor"

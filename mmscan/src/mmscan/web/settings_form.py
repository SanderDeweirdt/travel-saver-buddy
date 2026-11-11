"""The Settings page's editable config fields, one table for rendering, parsing and saving.

A field is only read when the form carries it (booleans carry a hidden `__seen` marker, because an
unticked box sends nothing), so a form that leaves a field out leaves its saved value alone."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from mmscan.config import Config

REGIONS = ("Europe", "Asia", "North America", "South America", "Africa", "Oceania")
CABINS = ("economy", "premium", "business", "first")


@dataclass(frozen=True)
class Field:
    group: str
    path: str  # "min_seats" or "section.field"
    label: str
    kind: str  # int | float | bool | text | date | codes | pairs | rates | cabins
    help: str = ""


FIELDS: tuple[Field, ...] = (
    Field("Scan", "cabins", "Cabins", "cabins", "Which cabins are scanned and shown."),
    Field(
        "Scan",
        "region_pairs",
        "Region pairs",
        "pairs",
        "One per line, like Europe > Asia. Asia > Asia is flights within Asia.",
    ),
    Field("Scan", "date_window.start_offset_days", "Window starts (days from today)", "int"),
    Field("Scan", "date_window.end_offset_days", "Window ends (days from today)", "int"),
    Field("Scan", "min_seats", "Seats needed", "int", "Flights with fewer seats are not offered."),
    Field(
        "Scan",
        "api.daily_call_cap",
        "Daily API call cap",
        "int",
        "seats.aero Pro allows 1000 a day.",
    ),
    Field(
        "Currencies",
        "usd_to_eur",
        "Euro per US dollar",
        "float",
        "Miles & More fees come in dollars.",
    ),
    Field("Currencies", "usd_to_eur_date", "Dollar rate checked on", "date", "YYYY-MM-DD."),
    Field(
        "Currencies",
        "fx_to_eur",
        "Euro per unit of other fee currencies",
        "rates",
        "One per line, like SGD = 0.67. A currency missing here is unpriced and hidden.",
    ),
    Field("Deals", "deals.min_saving_pct", "Best deals: minimum saving (%)", "float"),
    Field(
        "Deals", "deals.default_cabin", "Best deals: default cabin", "text", "Empty = all cabins."
    ),
    Field("Deals", "deals.by_ceiling", "Also a deal when under the benchmark ceiling", "bool"),
    Field(
        "Slack alerts",
        "notify.slack",
        "Post to Slack after each run",
        "bool",
        "The webhook URL stays a secret in SLACK_WEBHOOK_URL, never here.",
    ),
    Field(
        "Slack alerts",
        "notify.new_deals.enabled",
        "New-deal alert",
        "bool",
        "Post each flight the first time it is seen well below its usual price.",
    ),
    Field(
        "Slack alerts", "notify.new_deals.min_pct", "New deal: at least this % below usual", "float"
    ),
    Field("Slack alerts", "notify.new_deals.cabins", "New deal: cabins", "cabins"),
    Field(
        "Slack alerts",
        "notify.new_deals.unverified",
        "New deal: include dynamic-carrier prices",
        "bool",
        "Marked unverified in the message.",
    ),
    Field("Slack alerts", "notify.max_items", "Flights per message", "int", "1 to 40."),
    Field(
        "Slack alerts",
        "notify.on_drop",
        "Older alert: Cheaper results",
        "bool",
        "Inside the shortlist scope.",
    ),
    Field(
        "Slack alerts",
        "notify.verdicts",
        "Older alert: verdicts",
        "list",
        "Comma separated: Deal, Worth a look. Empty = none.",
    ),
    Field(
        "Slack alerts",
        "notify.changes",
        "Older alert: changes",
        "list",
        "Comma separated: New, Cheaper.",
    ),
    Field("Deals", "savings.great_pct", "Great: at least this % below usual", "float"),
    Field("Deals", "savings.good_pct", "Good: at least this % below usual", "float"),
    Field("Deals", "relative.percentile_good", "Good = cheapest percentile", "float"),
    Field("Deals", "relative.min_samples", "Prices needed for a usual price", "int"),
    Field("Deals", "relative.history_days", "History used (days)", "int"),
    Field("Deals", "relative.min_discount_pct", "Also at least this % below the median", "float"),
)


def _dig(cfg: Config, path: str) -> Any:
    obj: Any = cfg
    for part in path.split("."):
        obj = getattr(obj, part)
    return obj


def display(cfg: Config, f: Field) -> Any:
    v = _dig(cfg, f.path)
    if f.kind == "bool":
        return bool(v)
    if f.kind in ("cabins", "codes", "list"):
        return ", ".join(v)
    if f.kind == "pairs":
        return "\n".join(f"{p.origin} > {p.destination}" for p in v)
    if f.kind == "rates":
        return "\n".join(f"{k} = {r:g}" for k, r in sorted(v.items()))
    if v is None:
        return ""
    return f"{v:g}" if isinstance(v, float) else str(v)


def render_fields(cfg: Config, form=None) -> list[dict]:
    """Rows for the template; `form` (a failed save) wins over the config in force."""
    out = []
    for f in FIELDS:
        name = f"f__{f.path}"
        if form is not None and (name in form or f"{name}__seen" in form):
            value = bool(form.get(name)) if f.kind == "bool" else form.get(name, "")
        else:
            value = display(cfg, f)
        out.append({"f": f, "name": name, "value": value})
    return out


def _words(text: str) -> list[str]:
    return [w for w in text.replace(",", " ").split() if w]


def _num(text: str, kind: str, label: str, errors: list[str]) -> int | float | None:
    try:
        return int(text) if kind == "int" else float(text.replace(",", "."))
    except ValueError:
        errors.append(f"{label}: {text!r} is not a number")
        return None


def parse_fields(form, errors: list[str]) -> dict:
    """Saved-settings overrides for the fields the form carries."""
    out: dict[str, Any] = {}
    for f in FIELDS:
        name = f"f__{f.path}"
        if f.kind == "bool":
            if f"{name}__seen" not in form:
                continue
            value: Any = bool(form.get(name))
        elif name not in form:
            continue
        else:
            text = str(form.get(name) or "").strip()
            if f.kind in ("int", "float"):
                if not text:
                    continue  # empty: keep config.yaml's value
                value = _num(text, f.kind, f.label, errors)
                if value is None:
                    continue
            elif f.kind == "date":
                if not text:
                    continue
                try:
                    value = date.fromisoformat(text)
                except ValueError:
                    errors.append(f"{f.label}: {text!r} is not a date (YYYY-MM-DD)")
                    continue
            elif f.kind == "text":
                value = text
            elif f.kind == "codes":
                value = [w.upper() for w in _words(text)]
            elif f.kind == "list":
                value = [w.strip() for w in text.split(",") if w.strip()]
            elif f.kind == "cabins":
                value = [w.lower() for w in _words(text)]
            elif f.kind == "pairs":
                value = []
                for line in filter(None, (ln.strip() for ln in text.splitlines())):
                    a, sep, b = line.replace("→", ">").partition(">")
                    if not sep or not a.strip() or not b.strip():
                        errors.append(f"{f.label}: {line!r} should look like Europe > Asia")
                        continue
                    value.append({"origin": a.strip(), "destination": b.strip()})
            else:  # rates
                value = {}
                for line in filter(None, (ln.strip() for ln in text.splitlines())):
                    cur, sep, rate = line.replace(":", "=").partition("=")
                    num = _num(rate.strip(), "float", f"{f.label} ({cur.strip()})", errors)
                    if not sep or num is None or num <= 0:
                        errors.append(f"{f.label}: {line!r} should look like SGD = 0.67")
                        continue
                    value[cur.strip().upper()] = num
        if isinstance(value, date):
            value = value.isoformat()
        *parents, leaf = f.path.split(".")
        node = out
        for part in parents:
            node = node.setdefault(part, {})
        node[leaf] = value
    return out


BENCH_COLS = ("name", "cabin", "from", "to", "good_miles_max", "chart_rate_miles", "fees_max_eur")


def benchmark_rows(cfg: Config, form=None) -> list[dict]:
    """Table rows (plus one empty row to add a benchmark); a failed save's form wins."""
    if form is not None and "bm_seen" in form:
        rows, i = [], 0
        while f"bm__{i}__name" in form:
            rows.append(
                {c: form.get(f"bm__{i}__{c}", "") for c in BENCH_COLS}
                | {"remove": bool(form.get(f"bm__{i}__remove"))}
            )
            i += 1
        return rows
    rows = [
        {
            "name": b.name,
            "cabin": b.cabin,
            "from": b.between[0],
            "to": b.between[1],
            "good_miles_max": b.good_miles_max,
            "chart_rate_miles": b.chart_rate_miles,
            "fees_max_eur": f"{b.fees_max_eur:g}",
            "remove": False,
        }
        for b in cfg.benchmarks
    ]
    return [*rows, {c: "" for c in BENCH_COLS} | {"remove": False}]


def parse_benchmarks(form, errors: list[str]) -> list[dict] | None:
    """The benchmark list from the table, or None when the form has no table."""
    if "bm_seen" not in form:
        return None
    out, i = [], 0
    while f"bm__{i}__name" in form:
        row = {c: str(form.get(f"bm__{i}__{c}") or "").strip() for c in BENCH_COLS}
        i += 1
        if form.get(f"bm__{i - 1}__remove") or not any(row.values()):
            continue
        if not all(row.values()):
            errors.append(f"Benchmark {row['name'] or i}: fill in every column or clear the row")
            continue
        label = f"Benchmark {row['name']}"
        nums = {
            c: _num(row[c], "float" if c == "fees_max_eur" else "int", f"{label} {c}", errors)
            for c in ("good_miles_max", "chart_rate_miles", "fees_max_eur")
        }
        if any(v is None for v in nums.values()):
            continue
        out.append(
            {
                "name": row["name"],
                "cabin": row["cabin"].lower(),
                "between": [row["from"], row["to"]],
                **nums,
            }
        )
    return out

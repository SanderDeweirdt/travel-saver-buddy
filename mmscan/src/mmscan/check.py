"""`mmscan check`: four small calls that prove API access and record live responses."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mmscan.client import Client

FIXTURE_HEADERS = ("X-RateLimit-Remaining", "Content-Type")


def planned_check_requests() -> list[tuple[str, dict[str, Any]]]:
    search = {
        "origin_airport": "MUC",
        "destination_airport": "SIN",
        "sources": "lufthansa",
        "include_trips": True,
        "take": 10,
    }
    return [
        (
            "availability",
            {
                "source": "lufthansa",
                "cabin": "business",
                "origin_region": "Europe",
                "destination_region": "Asia",
                "take": 10,
            },
        ),
        ("trips/{first ID}", {}),
        ("search", search),
        ("search", {**search, "minify_trips": True}),
    ]


def _save(out_dir: Path, name: str, path: str, params: dict, resp, body: Any, key: str) -> Path:
    record = {
        "request": {"endpoint": "/" + path, "params": params},
        "status": resp.status_code,
        "headers": {h: resp.headers[h] for h in FIXTURE_HEADERS if h in resp.headers},
        "body": body,
    }
    text = json.dumps(record, indent=2, ensure_ascii=False)
    if key:
        text = text.replace(key, "REDACTED")
    out = out_dir / f"{name}.json"
    out.write_text(text + "\n")
    return out


def run_check(client: Client, out_dir: Path, api_key: str) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    plan = planned_check_requests()
    written: list[Path] = []

    path, params = plan[0]
    body, resp = client.get(path, params)
    written.append(_save(out_dir, "availability", path, params, resp, body, api_key))

    items = body.get("data") if isinstance(body, dict) else body
    first_id = items[0].get("ID") if items else None
    if first_id:
        path = f"trips/{first_id}"
        body, resp = client.get(path, {})
        written.append(_save(out_dir, "trips", path, {}, resp, body, api_key))

    for name, (path, params) in zip(("search", "search_minified"), plan[2:], strict=True):
        body, resp = client.get(path, params)
        written.append(_save(out_dir, name, path, params, resp, body, api_key))
    return written


def describe(paths: list[Path]) -> str:
    """Short, key-free overview of what came back, for the terminal."""
    lines = []
    for p in paths:
        rec = json.loads(p.read_text())
        body = rec["body"]
        top = sorted(body) if isinstance(body, dict) else f"list[{len(body)}]"
        items = body.get("data") if isinstance(body, dict) else body
        first = sorted(items[0]) if isinstance(items, list) and items else []
        lines.append(f"{p.name}: status {rec['status']}, top-level {top}")
        lines.append(f"  first item fields: {first}")
        lines.append(f"  X-RateLimit-Remaining: {rec['headers'].get('X-RateLimit-Remaining')}")
    return "\n".join(lines)

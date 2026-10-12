"""Inline-SVG line chart for a route's price history (no JS library, no CDN)."""

from __future__ import annotations

from datetime import datetime
from html import escape

W, H = 720, 280
PAD_L, PAD_R, PAD_T, PAD_B = 56, 90, 16, 32


def _ticks(lo: float, hi: float, n: int = 4) -> list[float]:
    if hi <= lo:
        return [lo]
    step = (hi - lo) / n
    return [lo + i * step for i in range(n + 1)]


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def price_chart(points: list[dict]) -> str:
    """`points`: dicts with `ts` (ISO), `low` and `median` (EUR). Two series: cheapest total per
    run and the median total. Colors come from CSS variables --series-1/--series-2."""
    if not points:
        return ""
    times = [_parse(p["ts"]).timestamp() for p in points]
    t0, t1 = min(times), max(times)
    values = [p[k] for p in points for k in ("low", "median")]
    lo, hi = min(values), max(values)
    pad = (hi - lo) * 0.1 or max(hi * 0.05, 1)
    lo, hi = max(0.0, lo - pad), hi + pad
    plot_w, plot_h = W - PAD_L - PAD_R, H - PAD_T - PAD_B

    def x(t: float) -> float:
        return PAD_L + (plot_w / 2 if t1 == t0 else (t - t0) / (t1 - t0) * plot_w)

    def y(v: float) -> float:
        return PAD_T + plot_h - (v - lo) / (hi - lo) * plot_h

    out = [
        f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" '
        'aria-label="Cheapest and median total cost per run">'
    ]
    for tick in _ticks(lo, hi):
        out.append(
            f'<line class="grid" x1="{PAD_L}" x2="{W - PAD_R}" '
            f'y1="{y(tick):.1f}" y2="{y(tick):.1f}"/>'
            f'<text class="axis" x="{PAD_L - 8}" y="{y(tick) + 4:.1f}" text-anchor="end">'
            f"{tick:,.0f}</text>"
        )
    for t in (t0, t1) if t1 != t0 else (t0,):
        label = datetime.fromtimestamp(t).strftime("%d %b")
        out.append(
            f'<text class="axis" x="{x(t):.1f}" y="{H - 8}" text-anchor="middle">{label}</text>'
        )
    for key, cls, name in (("median", "s2", "Median"), ("low", "s1", "Cheapest")):
        coords = [(x(t), y(p[key])) for t, p in zip(times, points, strict=True)]
        path = " ".join(
            f"{'M' if i == 0 else 'L'}{cx:.1f},{cy:.1f}" for i, (cx, cy) in enumerate(coords)
        )
        out.append(f'<path class="line {cls}" d="{path}"/>')
        lx, ly = coords[-1]
        out.append(
            f'<circle class="end {cls}" cx="{lx:.1f}" cy="{ly:.1f}" r="4"/>'
            f'<text class="label" x="{lx + 10:.1f}" y="{ly + 4:.1f}">{name}</text>'
        )
    for t, p in zip(times, points, strict=True):  # wide invisible hit targets for the tooltip
        tip = (
            f"{_parse(p['ts']).strftime('%d %b %H:%M')} UTC: cheapest {p['low']:,.0f} EUR, "
            f"median {p['median']:,.0f} EUR ({p['n']} results)"
        )
        out.append(
            f'<circle class="hit" cx="{x(t):.1f}" cy="{y(p["low"]):.1f}" r="12" '
            f'data-tip="{escape(tip)}"/>'
        )
    out.append("</svg>")
    return "".join(out)

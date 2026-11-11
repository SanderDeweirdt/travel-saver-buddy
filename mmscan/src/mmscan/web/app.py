"""Private, read-only dashboard over the mmscan database. Run with `mmscan web`."""

from __future__ import annotations

import csv
import io
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import quote

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from mmscan.config import Config, ConfigError, load_config
from mmscan.fares import CsvFareSource
from mmscan.links import mm_link
from mmscan.offers import ensure_current, rebuild_current
from mmscan.report import DISCLAIMER, SHORTLIST_COLUMNS, row_values, shortlist, write_report
from mmscan.store import FULL_RUNS, Store, read_overrides
from mmscan.web import queries
from mmscan.web.auth import LoginLimiter, password_ok
from mmscan.web.charts import price_chart
from mmscan.web.settings import WebSettings
from mmscan.web.settings_form import (
    benchmark_rows,
    parse_benchmarks,
    parse_fields,
    render_fields,
)

HERE = Path(__file__).parent
SORT_LABELS = {
    "pct": "Biggest % saving",
    "save": "Biggest € saving",
    "total": "Lowest price",
    "date": "Earliest date",
}
ROW_LIMIT = 300
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class LoginRequired(Exception):
    pass


def _fmt_money(v) -> str:
    return "–" if v is None else f"{v:,.0f}"


def _fmt_time(ts: str | None) -> str:
    if not ts:
        return "–"
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%d %b %H:%M")
    except ValueError:
        return ts


def create_app(settings: WebSettings) -> FastAPI:
    app = FastAPI(title="mmscan", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret,
        session_cookie="mmscan_session",
        max_age=14 * 24 * 3600,
        same_site="lax",
        https_only=settings.secure_cookies,
    )
    templates = Jinja2Templates(directory=str(HERE / "templates"))
    templates.env.filters["money"] = _fmt_money
    templates.env.filters["when"] = _fmt_time
    templates.env.globals["mm_link"] = lambda s, pax=1: mm_link(cfg, s, pax)
    limiter = LoginLimiter()
    cfg: Config = load_config(settings.config_path, read_overrides(settings.database))
    templates.env.globals["program_label"] = cfg.program_label
    boot = Store(settings.database)  # create the schema once; request handlers only read
    try:
        ensure_current(
            boot,
            cfg,
            datetime.now(UTC),
            CsvFareSource(settings.config_path.parent / "cash_fares.csv"),
        )
    finally:
        boot.close()

    def open_store():
        store = Store(settings.database, readonly=True)
        try:
            yield store
        finally:
            store.close()

    def require_login(request: Request) -> None:
        if not request.session.get("auth"):
            raise LoginRequired

    @app.exception_handler(LoginRequired)
    async def _to_login(request: Request, exc: LoginRequired):
        target = request.url.path + (f"?{request.url.query}" if request.url.query else "")
        return RedirectResponse(f"/login?next={quote(target, safe='')}", status_code=303)

    def render(request: Request, name: str, **ctx) -> HTMLResponse:
        ctx.update(disclaimer=DISCLAIMER, page=name.removesuffix(".html"))
        return templates.TemplateResponse(request, name, ctx)

    @app.get("/healthz", response_class=PlainTextResponse)
    def healthz() -> str:
        return "ok"

    @app.get("/login", response_class=HTMLResponse)
    def login_form(request: Request, next: str = "/"):
        return render(request, "login.html", next=next, error=None)

    @app.post("/login")
    def login(request: Request, password: str = Form(""), next: str = Form("/")):
        client = request.client.host if request.client else "?"
        if limiter.blocked(client):
            return render(request, "login.html", next=next, error="Too many attempts. Wait.")
        if not password_ok(password, settings.password):
            limiter.fail(client)
            resp = render(request, "login.html", next=next, error="Wrong password.")
            resp.status_code = 401
            return resp
        limiter.reset(client)
        request.session["auth"] = True
        safe = next if next.startswith("/") and not next.startswith("//") else "/"
        return RedirectResponse(safe, status_code=303)

    def _number(raw: str | None, label: str, errors: list[str]) -> float | None:
        text = (raw or "").strip().replace(",", ".")
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            errors.append(f"{label}: {raw!r} is not a number")
            return None

    def settings_rows() -> list[dict]:
        """One row per program in `programs`, from the config in force."""
        return [
            {
                "id": key,
                "label": cfg.program_label(key),
                "bookable": p.enabled,
                "cost": "" if p.mile_cost_eur_cents is None else f"{p.mile_cost_eur_cents:g}",
                "mr": "" if p.mr_per_mile is None else f"{p.mr_per_mile:g}",
                "within": p.within_region,
                "effective": cfg.mile_cents(key),
            }
            for key, p in sorted(cfg.programs.items())
        ]

    def settings_ctx(**extra) -> dict:
        store = Store(settings.database, readonly=True)
        try:
            health = queries.data_view(store, cfg, datetime.now(UTC))
        finally:
            store.close()
        return {
            "d": health,
            "cfg": cfg,
            "main_label": cfg.program_label(cfg.source),
            "mm_cost": f"{cfg.mile_cost_eur_cents:g}",
            "mr_value": ""
            if cfg.mr_point_value_eur_cents is None
            else f"{cfg.mr_point_value_eur_cents:g}",
            "rows": settings_rows(),
            "fields": render_fields(cfg),
            "benchmarks": benchmark_rows(cfg),
            "errors": [],
            "saved": False,
            **extra,
        }

    @app.get("/settings", response_class=HTMLResponse, dependencies=[Depends(require_login)])
    def settings_page(request: Request, saved: int = 0):
        return render(request, "settings.html", **settings_ctx(saved=bool(saved)))

    @app.post("/settings", dependencies=[Depends(require_login)])
    async def settings_save(request: Request):
        nonlocal cfg
        form = await request.form()
        errors: list[str] = []
        mm_cost = _number(form.get("mile_cost_eur_cents"), "Miles & More mile value", errors)
        mr_value = _number(form.get("mr_point_value_eur_cents"), "Amex point value", errors)
        programs: dict[str, dict] = {}
        for key in cfg.programs:
            programs[key] = {
                "enabled": bool(form.get(f"bookable__{key}")),
                "mile_cost_eur_cents": _number(form.get(f"cost__{key}"), f"{key} cost", errors),
                "mr_per_mile": _number(form.get(f"mr__{key}"), f"{key} points per mile", errors),
            }
            if f"withinseen__{key}" in form:
                programs[key]["within_region"] = bool(form.get(f"within__{key}"))
        if mm_cost is None:
            errors.append("Miles & More mile value is required")
        overrides = {
            "mile_cost_eur_cents": mm_cost,
            "mr_point_value_eur_cents": mr_value,
            "programs": programs,
            **parse_fields(form, errors),
        }
        benchmarks = parse_benchmarks(form, errors)
        if benchmarks is not None:
            overrides["benchmarks"] = benchmarks
        new_cfg = None
        if not errors:
            try:
                new_cfg = load_config(settings.config_path, overrides)
            except ConfigError as e:
                errors.append(str(e))
        if errors:
            rows = [
                {
                    "id": k,
                    "label": cfg.program_label(k),
                    "bookable": bool(form.get(f"bookable__{k}")),
                    "cost": form.get(f"cost__{k}", ""),
                    "mr": form.get(f"mr__{k}", ""),
                    "within": bool(form.get(f"within__{k}")),
                    "effective": None,
                }
                for k in sorted(cfg.programs)
            ]
            resp = render(
                request,
                "settings.html",
                **settings_ctx(
                    errors=errors,
                    rows=rows,
                    fields=render_fields(cfg, form),
                    benchmarks=benchmark_rows(cfg, form),
                    mm_cost=form.get("mile_cost_eur_cents", ""),
                    mr_value=form.get("mr_point_value_eur_cents", ""),
                ),
            )
            resp.status_code = 422
            return resp
        store = Store(settings.database)
        try:
            store.set_overrides(overrides)
            cfg = new_cfg
            templates.env.globals["program_label"] = cfg.program_label
            rebuild_current(
                store,
                cfg,
                0,
                datetime.now(UTC),
                CsvFareSource(settings.config_path.parent / "cash_fares.csv"),
            )
        finally:
            store.close()
        return RedirectResponse("/settings?saved=1", status_code=303)

    @app.post("/logout")
    def logout(request: Request):
        request.session.clear()
        return RedirectResponse("/login", status_code=303)

    def deals_context(store: Store, q: dict, *, min_pct: float | None, inline: bool) -> dict:
        """Shared by Best deals and All routes: one row per flight, every route."""
        cabin = q["cabin"]
        cabin = cfg.deals.default_cabin if cabin is None else ("" if cabin == "all" else cabin)
        pax = max(1, min(q["pax"] or 1, 9))
        hide_chart = bool(q["nochart"])
        f = {
            "cabin": cabin,
            "direction": q["direction"],
            "route": q["route"],
            "origin": q["origin"],
            "destination": q["destination"],
            "pax": pax,
            "sort": q["sort"],
            "chart": int(bool(q["chart"]) and not hide_chart),
            "nochart": int(hide_chart),
            "fresh": q["fresh"],
            "min_pct": min_pct,
            "limit": max(50, min(q["limit"], 20000)),
        }
        updated = queries.last_update(store)
        view = None
        if updated is not None:
            view = queries.deals_view(
                store,
                cfg,
                datetime.now(UTC),
                direction=q["direction"],
                cabin=cabin,
                route=q["route"],
                origin=q["origin"],
                destination=q["destination"],
                pax=pax,
                sort=q["sort"],
                chart_only=bool(f["chart"]),
                hide_chart=hide_chart,
                min_pct=min_pct,
                inline_building=inline,
                hide_stale=bool(q["fresh"]),
            )
            view["rows_total"] = len(view["deals"])
            view["deals"] = view["deals"][: f["limit"]]  # a month of flights is megabytes of HTML
        return {
            "view": view,
            "updated": updated,
            "cabins": cfg.cabins,
            "sorts": SORT_LABELS,
            "f": f,
        }

    @app.get("/", dependencies=[Depends(require_login)])
    def home():
        return RedirectResponse("/overview", status_code=303)

    @app.get("/overview", response_class=HTMLResponse, dependencies=[Depends(require_login)])
    def overview_page(
        request: Request,
        store: Store = Depends(open_store),
        cabin: str | None = None,
        direction: str = "",
        route: str = "",
        origin: str = "",
        destination: str = "",
        pax: int | None = None,
        sort: str = "pct",
        chart: int = 0,
        nochart: int = 0,
        fresh: int = 1,
        limit: int = ROW_LIMIT,
    ):
        q = dict(
            cabin=cabin, direction=direction, route=route, origin=origin.strip(),
            destination=destination.strip(), pax=pax, sort=sort,
            chart=chart, nochart=nochart, fresh=fresh, limit=limit,
        )  # fmt: skip
        ctx = deals_context(store, q, min_pct=None, inline=True)
        return render(request, "overview.html", **ctx)

    MAX_WATCH_ITEMS = 50  # each one costs API calls on every scan

    def watchlist_ctx(store: Store, q: dict | None = None, **extra) -> dict:
        today = datetime.now(UTC).date().isoformat()
        q = q or {}
        cabin = q.get("cabin")
        cabin = "" if cabin in (None, "all") else cabin
        pax = max(1, min(q.get("pax") or 1, 9))
        sort = q.get("sort") if q.get("sort") in queries.WATCH_SORTS else "date"
        f = {
            "cabin": cabin,
            "origin": (q.get("origin") or "").strip(),
            "destination": (q.get("destination") or "").strip(),
            "pax": pax,
            "sort": sort,
        }
        view = queries.watch_items_view(
            store, cfg, store.watch_items(), today,
            cabin=cabin, origin=f["origin"], destination=f["destination"], pax=pax, sort=sort,
        )  # fmt: skip
        return {
            "items": view["items"],
            "places": view["places"],
            "cabins": cfg.cabins,
            "sorts": queries.WATCH_SORTS,
            "f": f,
            "updated": queries.last_update(store),
            "today": today,
            "max_items": MAX_WATCH_ITEMS,
            "errors": [],
            "form": {},
            **extra,
        }

    @app.get("/watchlist", response_class=HTMLResponse, dependencies=[Depends(require_login)])
    @app.get("/shortlist", response_class=HTMLResponse, dependencies=[Depends(require_login)])
    def watchlist_page(
        request: Request,
        store: Store = Depends(open_store),
        added: int = 0,
        cabin: str | None = None,
        origin: str = "",
        destination: str = "",
        pax: int | None = None,
        sort: str = "date",
    ):
        q = dict(cabin=cabin, origin=origin, destination=destination, pax=pax, sort=sort)
        return render(request, "watchlist.html", **watchlist_ctx(store, q, added=bool(added)))

    def _airport(raw: str | None, label: str, errors: list[str]) -> str:
        code = (raw or "").strip().upper()
        if not (len(code) == 3 and code.isalpha() and code.isascii()):
            errors.append(f"{label} must be a three-letter airport code such as FRA")
        return code

    def _day(raw: str | None, label: str, errors: list[str]) -> str:
        try:
            return date.fromisoformat((raw or "").strip()).isoformat()
        except ValueError:
            errors.append(f"{label} must be a date")
            return ""

    @app.post("/watchlist", dependencies=[Depends(require_login)])
    async def watchlist_add(request: Request):
        form = await request.form()
        errors: list[str] = []
        origin = _airport(form.get("origin"), "From", errors)
        destination = _airport(form.get("destination"), "To", errors)
        first = _day(form.get("date_from"), "Departure date", errors)
        last = _day(form.get("date_to") or form.get("date_from"), "Latest departure", errors)
        today = datetime.now(UTC).date().isoformat()
        if not errors:
            if origin == destination:
                errors.append("From and To must differ")
            if last < first:
                errors.append("The latest departure is before the earliest")
            if last < today:
                errors.append("That date has already passed")
        store = Store(settings.database)
        try:
            items = store.watch_items()
            if not errors and len(items) >= MAX_WATCH_ITEMS:
                errors.append(f"The watchlist is full ({MAX_WATCH_ITEMS}); remove one first")
            if not errors and any(
                (i["origin"], i["destination"], i["date_from"], i["date_to"])
                == (origin, destination, first, last)
                for i in items
            ):
                errors.append("That flight is already on the watchlist")
            if not errors:
                store.add_watch_item(origin, destination, first, last)
                return RedirectResponse("/watchlist?added=1", status_code=303)
        finally:
            store.close()
        read = Store(settings.database, readonly=True)
        try:
            ctx = watchlist_ctx(
                read,
                errors=errors,
                form={
                    "origin": origin,
                    "destination": destination,
                    "date_from": form.get("date_from", ""),
                    "date_to": form.get("date_to", ""),
                },
            )
        finally:
            read.close()
        resp = render(request, "watchlist.html", **ctx)
        resp.status_code = 422
        return resp

    @app.post("/watchlist/{item_id}/delete", dependencies=[Depends(require_login)])
    def watchlist_delete(item_id: int):
        store = Store(settings.database)
        try:
            store.delete_watch_item(item_id)
        finally:
            store.close()
        return RedirectResponse("/watchlist", status_code=303)

    @app.get(
        "/watchlist/{item_id}", response_class=HTMLResponse, dependencies=[Depends(require_login)]
    )
    def watchlist_item_page(request: Request, item_id: int, store: Store = Depends(open_store)):
        item = store.watch_item(item_id)
        if item is None:
            raise HTTPException(404, "That watchlist item does not exist.")
        view = queries.watch_item_view(store, cfg, item, datetime.now(UTC))
        return render(request, "watchlist_item.html", item=item, view=view)

    @app.get(
        "/route/{origin}/{destination}/{cabin}",
        response_class=HTMLResponse,
        dependencies=[Depends(require_login)],
    )
    def route_page(
        request: Request,
        origin: str,
        destination: str,
        cabin: str,
        store: Store = Depends(open_store),
    ):
        data = queries.route_history(store, cfg, origin, destination, cabin, datetime.now(UTC))
        return render(
            request,
            "route.html",
            origin=origin,
            destination=destination,
            cabin=cabin,
            chart=price_chart(data["points"], data["usual"].median if data["usual"] else None),
            **data,
        )

    @app.get("/data", dependencies=[Depends(require_login)])
    def data_page():
        return RedirectResponse("/settings", status_code=303)

    @app.get("/runs", response_class=HTMLResponse, dependencies=[Depends(require_login)])
    def runs_page(request: Request, store: Store = Depends(open_store)):
        return render(request, "runs.html", runs=queries.recent_runs(store))

    @app.get("/quota", response_class=HTMLResponse, dependencies=[Depends(require_login)])
    def quota_page(request: Request, store: Store = Depends(open_store)):
        q = queries.quota_view(store, cfg.api.daily_call_cap, datetime.now(UTC))
        return render(request, "quota.html", q=q)

    def _latest(store: Store) -> int:
        run_id = store.latest_scanned_run(FULL_RUNS)
        if run_id is None or queries.last_update(store) is None:
            raise HTTPException(404, "No prices yet.")
        return run_id

    @app.get("/reports/latest.xlsx", dependencies=[Depends(require_login)])
    def report_xlsx(store: Store = Depends(open_store)):
        run_id, now = _latest(store), datetime.now(UTC)
        report_cfg = cfg.model_copy(deep=True)
        with tempfile.TemporaryDirectory() as tmp:
            report_cfg.output.dir = Path(tmp)
            report_cfg.output.formats = ["xlsx"]
            (path,) = write_report(store, report_cfg, run_id, now)
            body = path.read_bytes()
        return Response(
            body,
            media_type=XLSX,
            headers={"Content-Disposition": 'attachment; filename="mmscan_latest.xlsx"'},
        )

    @app.get("/reports/latest-shortlist.csv", dependencies=[Depends(require_login)])
    def report_csv(store: Store = Depends(open_store)):
        from mmscan.offers import load_current

        _latest(store)
        now = datetime.now(UTC)
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(SHORTLIST_COLUMNS)
        for s in shortlist(load_current(store), cfg):
            w.writerow(["" if v is None else v for v in row_values(s, cfg, now)])
        return Response(
            buf.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="mmscan_latest_shortlist.csv"'},
        )

    return app

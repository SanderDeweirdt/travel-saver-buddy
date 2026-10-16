"""Private, read-only dashboard over the mmscan database. Run with `mmscan web`."""

from __future__ import annotations

import csv
import io
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from mmscan.config import Config, load_config
from mmscan.report import DISCLAIMER, SHORTLIST_COLUMNS, row_values, shortlist, write_report
from mmscan.store import Store
from mmscan.trips import age_hours, calendar_cells, trip_trend, trip_views
from mmscan.web import queries
from mmscan.web.auth import LoginLimiter, password_ok
from mmscan.web.charts import price_chart, sparkline
from mmscan.web.settings import WebSettings

HERE = Path(__file__).parent
SORT_LABELS = {
    "pct": "Biggest % saving",
    "save": "Biggest € saving",
    "total": "Lowest price",
    "date": "Earliest date",
}
OVERVIEW_SORTS = {
    "route": "Route",
    "total": "Lowest price",
    "pct": "Biggest % below usual",
    "date": "Earliest date",
    "count": "Most dates",
}
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
    limiter = LoginLimiter()
    cfg: Config = load_config(settings.config_path)
    Store(settings.database).close()  # create the schema once; request handlers only read

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

    @app.post("/logout")
    def logout(request: Request):
        request.session.clear()
        return RedirectResponse("/login", status_code=303)

    @app.get("/", response_class=HTMLResponse, dependencies=[Depends(require_login)])
    def deals_page(
        request: Request,
        store: Store = Depends(open_store),
        cabin: str | None = None,
        route: str = "",
        pax: int | None = None,
        sort: str = "pct",
        chart: int = 0,
        fresh: int = 1,
    ):
        now = datetime.now(UTC)
        if cabin is None:
            cabin = cfg.deals.default_cabin
        elif cabin == "all":
            cabin = ""
        run_id = store.latest_scored_run()
        pax = max(1, min(pax or cfg.min_seats, 9))
        view = None
        if run_id is not None:
            view = queries.deals_view(
                store,
                cfg,
                run_id,
                now,
                cabin=cabin,
                route=route,
                pax=pax,
                sort=sort,
                chart_only=bool(chart),
                hide_stale=bool(fresh),
            )
        return render(
            request,
            "deals.html",
            view=view,
            run_id=run_id,
            run=store.run_info(run_id) if run_id else None,
            cabins=cfg.cabins,
            sorts=SORT_LABELS,
            cfg_days=cfg.relative.history_days,
            cfg_min=cfg.relative.min_samples,
            cfg_good=f"{cfg.savings.good_pct:g}",
            cfg_great=f"{cfg.savings.great_pct:g}",
            mile_ct=cfg.mile_cost_eur_cents,
            f={
                "cabin": cabin,
                "route": route,
                "pax": pax,
                "sort": sort,
                "chart": chart,
                "fresh": fresh,
            },
        )

    @app.get("/overview", response_class=HTMLResponse, dependencies=[Depends(require_login)])
    def overview_page(
        request: Request,
        store: Store = Depends(open_store),
        cabin: str | None = None,
        direction: str = "",
        route: str = "",
        sort: str = "route",
        fresh: int = 1,
    ):
        if cabin is None:
            cabin = cfg.deals.default_cabin
        elif cabin == "all":
            cabin = ""
        run_id = store.latest_scored_run()
        view = None
        if run_id is not None:
            view = queries.overview_view(
                store,
                cfg,
                run_id,
                datetime.now(UTC),
                cabin=cabin,
                direction=direction,
                route=route,
                sort=sort,
                hide_stale=bool(fresh),
            )
        return render(
            request,
            "overview.html",
            view=view,
            run_id=run_id,
            run=store.run_info(run_id) if run_id else None,
            cabins=cfg.cabins,
            sorts=OVERVIEW_SORTS,
            f={
                "cabin": cabin,
                "direction": direction,
                "route": route,
                "sort": sort,
                "fresh": fresh,
            },
        )

    @app.get("/shortlist", response_class=HTMLResponse, dependencies=[Depends(require_login)])
    def shortlist_page(
        request: Request,
        store: Store = Depends(open_store),
        run: int | None = None,
        route: str = "",
        cabin: str = "",
        verdict: str = "",
        sort: str = "verdict",
        all: int = 0,
    ):
        now = datetime.now(UTC)
        run_id = run or store.latest_scored_run()
        view = None
        if run_id is not None:
            view = queries.shortlist_view(
                store, cfg, run_id, now, route, cabin, verdict, sort, bool(all)
            )
        return render(
            request,
            "shortlist.html",
            view=view,
            run_id=run_id,
            run=store.run_info(run_id) if run_id else None,
            runs=queries.scored_runs(store),
            f={"route": route, "cabin": cabin, "verdict": verdict, "sort": sort, "all": all},
            sorts=list(queries.SORTS),
        )

    @app.get("/trips", response_class=HTMLResponse, dependencies=[Depends(require_login)])
    def trips_page(request: Request, store: Store = Depends(open_store), show: int = 12):
        now = datetime.now(UTC)
        views = trip_views(store, cfg, now)
        extras = {}
        for v in views:
            trend = trip_trend(store, cfg, v.profile, now)
            totals = [p["total"] for p in trend]
            extras[v.profile.name] = {
                "spark": sparkline(
                    totals,
                    f"Best price for {v.seats} travellers over the last 30 days: "
                    f"{totals[0]:,.0f} to {totals[-1]:,.0f} euro"
                    if totals
                    else "",
                ),
                "trend": trend,
                "calendar": calendar_cells(v) if v.pairs else None,
            }
        return render(
            request,
            "trips.html",
            views=views,
            extras=extras,
            cfg_unverified=cfg.notify.unverified,
            pricing_model=cfg.pricing_model,
            now=now,
            age_hours=age_hours,
            show=max(1, min(show, 200)),
            freshness=cfg.trip_freshness_hours,
        )

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

    @app.get("/data", response_class=HTMLResponse, dependencies=[Depends(require_login)])
    def data_page(request: Request, store: Store = Depends(open_store)):
        return render(
            request, "data.html", d=queries.data_view(store, cfg, datetime.now(UTC)), cfg=cfg
        )

    @app.get("/runs", response_class=HTMLResponse, dependencies=[Depends(require_login)])
    def runs_page(request: Request, store: Store = Depends(open_store)):
        return render(request, "runs.html", runs=queries.recent_runs(store))

    @app.get("/quota", response_class=HTMLResponse, dependencies=[Depends(require_login)])
    def quota_page(request: Request, store: Store = Depends(open_store)):
        q = queries.quota_view(store, cfg.api.daily_call_cap, datetime.now(UTC))
        return render(request, "quota.html", q=q)

    def _latest(store: Store) -> int:
        run_id = store.latest_scored_run()
        if run_id is None:
            raise HTTPException(404, "No scored run yet.")
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
        from mmscan.report import load_results

        run_id, now = _latest(store), datetime.now(UTC)
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(SHORTLIST_COLUMNS)
        for s in shortlist(load_results(store, run_id), cfg):
            w.writerow(["" if v is None else v for v in row_values(s, cfg, now)])
        return Response(
            buf.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="mmscan_latest_shortlist.csv"'},
        )

    return app

"""Analytics (#/analytics; docs/BACKEND_STEPS.md, B14): the closed decisions the account may see, their totals and the
model versions' accuracy.

    GET /api/screens/analytics?tenant=&cls=&route=&from=0&to=11&model=&tenant_filter=All
        rows                  the closed decisions (the demo's ROWS) in the account's tenants, narrowed by the page's
                              filters (AnalyticsFilter) and the top bar's tenant filter (tenant_filter: All or a tenant):
                              the demo's aRows(), in ROWS order, each row as the demo has it
        metrics               the demo's metrics(rows) without `rc`: rc is rows.filter(r => r.status === 'reconciled'),
                              in the same order (the frontend rebuilds it; sending it twice doubles the answer)
        model_stats           the demo's modelStats(v) for each model version (MODELS order; null where it has no
                              reconciled decisions); over every closed decision, as in the demo, not only the account's
        telemetry_unavailable the ESG telemetry source (iot) is not connected: read from the backend's source_system
                              table (the real connector state), which agrees with the demo's SRC('iot')
    POST /api/actions/analytics.models   the read action the page's agent answer calls (registered here; it had no
                              handler before B14): the demo's handler, over every reconciled decision

Charts (waterfall, pipeline, route mix, predicted vs actual, overrides, engineering heat map, sustainability, pool
efficiency) and the drill-through are drawn from `rows` and `metrics` in the frontend (pages/analytics/charts.tsx), as
they are today: every number on the page is a sum or count over these rows, and the drill-through needs the rows.

The page is for accounts that may open Analytics (canPage('analytics')); others get 403.

Facade mapping (apps/web/src/api/analytics.ts), for the switch-over (B17):

| export                         | served by                                                                   |
|--------------------------------|-----------------------------------------------------------------------------|
| analyticsRows(f)               | endpoint: GET /api/screens/analytics (rows), f as query parameters           |
| metrics(rows)                  | endpoint: same answer (metrics; rc = rows with status 'reconciled')         |
| modelStats(v)                  | endpoint: same answer (model_stats, in MODELS order)                         |
| telemetryUnavailable()         | endpoint: same answer (telemetry_unavailable)                                |
| modelAccuracy()                | endpoint: POST /api/actions/analytics.models (registered in this module)     |
| closedRow(id)                  | frontend-only: find the row in `rows` (the drawer opens from the drill list) |
| months()                       | reference: MONTHS                                                            |
| routes()                       | reference: ROUTES                                                            |
| modelVersions()                | reference: MODELS                                                            |
| assetClasses()                 | reference: CLASSES                                                           |
| classIcon(cls)                 | reference: CLS_ICON                                                          |
| equipmentModels()              | reference: EQUIP (.m)                                                        |
| components()                   | reference: COMPS                                                             |
| journeyStep(n)                 | reference: JSTEPS[JMAP[n] - 1] (JMAP[n] is n itself beyond 12)               |
| routeById(id)                | frontend-only: lookup in ROUTES (reference)                                  |
| kfmt, pct, sum, DEFAULT_FILTER | frontend-only: formatting and the page's default filter                     |
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from di import golden
from di.actions.pipeline import Actor, CallContext
from di.actions.registry import implement
from di.auth import Principal, principal
from di.cases import store
from di.db import get_session
from di.engine.jsmath import js_round, js_sum
from di.reads.common import WORLD, to_fixed, vis_cases

router = APIRouter(prefix="/api/screens/analytics", tags=["screens: analytics"])
MODELS = WORLD["models"]
ROUTES = WORLD["routes"]


# ---------------------------------------------------------------- the closed decisions (the demo's ROWS)
def all_rows() -> list[dict]:
    return golden.load("decisions")


def vis_rows(p: Principal, tenant_filter: str = "All") -> list[dict]:
    """The demo's visRows: the closed decisions in the account's tenants and the top bar's tenant filter."""
    return [r for r in all_rows() if p.tenant_ok(r["tenant"]) and (tenant_filter == "All" or r["tenant"] == tenant_filter)]


def call_context(p: Principal, session: Session) -> CallContext:
    """The context the read helpers in di.reads take, for the signed-in account."""
    return CallContext(actor=Actor(account=p.account, ctx=p.ctx), session=session)


def vis_cases_filtered(ctx: CallContext, tenant_filter: str = "All") -> list[dict]:
    """The demo's visCases with the top bar's tenant filter (S.tenant)."""
    return [c for c in vis_cases(ctx, store.all_cases(ctx.session)) if tenant_filter == "All" or c["owner"] == tenant_filter]


def med(a: list[float]) -> float:
    """The demo's med."""
    if not a:
        return 0
    s, m = sorted(a), len(a) >> 1
    return s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2


def metrics(rows: list[dict], live_open: int) -> dict:
    """The demo's metrics(rows), without rc (the reconciled rows). live_open: visible cases awaiting approval."""
    rc = [r for r in rows if r["status"] == "reconciled"]
    base, act = js_sum(r["baseline"] for r in rc), js_sum(r["actual"] for r in rc)
    pend = sum(1 for r in rows if r["status"] == "pending")
    return {
        "base": base,
        "act": act,
        "uplift": act - base,
        "avoided": js_sum(r["avoided"] for r in rc),
        "days": med([r["days"] for r in rc]),
        "baseDays": med([r["baseDays"] for r in rc]),
        "pend": pend,
        "liveOpen": live_open,
        "unresolved": pend + live_open,
        "canc": sum(1 for r in rows if r["status"] == "cancelled"),
        "exp": sum(1 for r in rows if r["status"] == "expired"),
        "n": len(rows),
    }


def reconciled() -> list[dict]:
    """The demo's REC(): every reconciled closed decision (all tenants)."""
    return [r for r in all_rows() if r["status"] == "reconciled"]


def model_stats(v: str) -> dict | None:
    """The demo's modelStats(v): error, bias and P10-P90 coverage of a model version (exit routes and overrides out)."""
    r = [x for x in reconciled() if x["model"] == v and x["route"] != "exit" and not x.get("override")]
    n = len(r)
    if not n:
        return None
    mape = js_sum(abs(x["actual"] - x["p50"]) / max(abs(x["p50"]), 1) for x in r) / n
    bias = js_sum((x["actual"] - x["p50"]) / max(abs(x["p50"]), 1) for x in r) / n
    cov = sum(1 for x in r if x["p10"] <= x["actual"] <= x["p90"]) / n
    return {"v": v, "n": n, "mape": mape, "bias": bias, "cov": cov}


def _fixed1(x: float) -> float:
    """`+x.toFixed(1)`, for either sign."""
    return float(("-" if x < 0 else "") + to_fixed(abs(x), 1))


@implement("analytics.models")
def analytics_models(i, ctx):  # noqa: ARG001 - read handlers take (input, ctx)
    """The demo's analytics.models: each model version against outcomes, and how many landed within ±10%."""
    ms = [(m, s) for m in MODELS if (s := model_stats(m["v"]))]
    rc = [x for x in reconciled() if x["route"] != "exit" and not x.get("override")]
    band = 10
    inb = sum(1 for x in rc if abs(x["actual"] - x["p50"]) / max(abs(x["p50"]), 1) <= band / 100)
    return {
        "decisions": len(rc),
        "band_pct": band,
        "within_band": inb,
        "within_band_pct": js_round(inb / max(1, len(rc)) * 100),
        "target_coverage_pct": 80,
        "versions": [
            {
                "version": m["v"],
                "released": m["released"],
                "decisions": s["n"],
                "error_pct": _fixed1(s["mape"] * 100),
                "bias_pct": _fixed1(s["bias"] * 100),
                "coverage_pct": js_round(s["cov"] * 100),
            }
            for m, s in ms
        ],
    }


def telemetry_unavailable(session: Session) -> bool:
    """The ESG telemetry source (iot) is not connected (the connector's state; a source not set up counts as not)."""
    st = session.execute(text("SELECT status FROM source_system WHERE id = 'iot'")).scalar()
    return (st or "unavailable") == "unavailable"


@router.get("")
def analytics(
    tenant: str = "",
    cls: str = "",
    route: str = "",
    from_: int = Query(0, alias="from"),
    to: int = 11,
    model: str = "",
    tenant_filter: str = "All",
    p: Principal = Depends(principal),
    session: Session = Depends(get_session),
):
    p.require_page("analytics")
    rows = [
        r
        for r in vis_rows(p, tenant_filter)
        if (not tenant or r["tenant"] == tenant)
        and (not cls or r["cls"] == cls)
        and (not route or r["route"] == route)
        and from_ <= r["mi"] <= to
        and (not model or r["model"] == model)
    ]
    live = sum(1 for c in vis_cases_filtered(call_context(p, session), tenant_filter) if c["stage"] == "awaiting_approval")
    return {
        "rows": rows,
        "metrics": metrics(rows, live),
        "model_stats": [model_stats(m["v"]) for m in MODELS],
        "telemetry_unavailable": telemetry_unavailable(session),
    }

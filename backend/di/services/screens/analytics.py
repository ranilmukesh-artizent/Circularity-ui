"""Analytics (#/analytics; docs/backend-steps.md, B14): the closed decisions the account may see, their totals and the
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
        orgs                  plan 8 MVP-10.1: the org units the account may pick in the page's org select (depth
                              first, with their depth); `org=<unit>` narrows rows and metrics to the unit's subtree
                              (the group roll-up: `workspace` is every case). No `org`: the demo's answer.
    GET /api/screens/analytics/pack?key=   plan 9 P9-1.13: the "Packs" tab, from the pack's own data (`pack_view`):
                              `key` (the pack shown; empty: the first pack with KPIs and visible cases, else industrial), `name`,
                              `cases` (how many of its cases the account sees), `worked_questions` ([{id, question}], asked
                              through `device.question`), `renewals` (the pack has contract renewals), `packs` ([{key,
                              name}] to pick from, industrial first), `kpis` (id, label, value, unit, trend, error; see
                              di.services.modeler.kpis), `questions` (the pack's analytics questions answered: rows of
                              {key, value} and up to 5 example case ids), `suggestion_rules` (as configured) and `stages`
                              ([{key, label, agent, autonomy}]), over the cases of that pack the account may see. The
                              page's own answer above is unchanged.
    GET /api/screens/analytics/renewals?since=&until=   plan 9 P9-5.7: "Contract renewals": `with_proposal` and
                              `without_proposal` ({n, renewed, rate}), `segments` (market and size band, each with both),
                              `compared` (what the proposals predicted against the recorded outcomes: n, predicted_rate,
                              actual_rate, fee_error_pct, swaps_accepted), `basis` and the `caveat`, verbatim. Over the
                              account's org units; no model writes any of it. The facade's renewalReport.
    POST /api/actions/analytics.models   the read action the page's agent answer calls (registered here; it had no
                              handler before B14): the demo's handler, over every reconciled decision

Charts (waterfall, pipeline, route mix, predicted vs actual, overrides, engineering heat map, sustainability, pool
efficiency) and the drill-through are drawn from `rows` and `metrics` in the frontend (pages/analytics/AnalyticsCharts.tsx), as
they are today: every number on the page is a sum or count over these rows, and the drill-through needs the rows.

The page is for accounts that may open Analytics (canPage('analytics')); others get 403. The endpoint is in
di.routes.screens.analytics; this module builds what it returns.

Facade mapping (frontend/src/api/analytics.ts), for the switch-over (B17):

| export                         | served by                                                                   |
|--------------------------------|-----------------------------------------------------------------------------|
| analyticsRows(f)               | endpoint: GET /api/screens/analytics (rows), f as query parameters           |
| metrics(rows)                  | endpoint: same answer (metrics; rc = rows with status 'reconciled')         |
| modelStats(v)                  | endpoint: same answer (model_stats, in MODELS order)                         |
| telemetryUnavailable()         | endpoint: same answer (telemetry_unavailable)                                |
| analyticsOrgs()                | endpoint: same answer (orgs; plan 8 MVP-10.1), `org` in the filter           |
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

from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core import orgs, policy
from di.core.auth import Principal
from di.repositories import renewals as renewals_repo
from di.repositories.common import to_fixed
from di.repositories.constants import MODELS
from di.repositories.context import call_ctx, visible_cases, visible_rows
from di.repositories.decisions import model_stats, reconciled
from di.repositories.packs import active_pack, published_keys
from di.services import questions  # noqa: F401  (registers every pack's worked questions)
from di.services.actions.pipeline import CallContext
from di.services.actions.registry import implement
from di.services.device import analytics as worked
from di.services.engine.jsmath import js_round, js_sum
from di.services.modeler import kpis
from di.services.modeler.pack import Pack, pack_keys
from di.services.questions import worked_questions

# ---------------------------------------------------------------- the closed decisions (the demo's ROWS)


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


def _fixed1(x: float) -> float:
    """`+x.toFixed(1)`, for either sign."""
    return float(("-" if x < 0 else "") + to_fixed(abs(x), 1))


@implement("analytics.models")
def analytics_models(i: dict[str, Any], ctx: CallContext):  # noqa: ARG001 - read handlers take (input, ctx)
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


def actor_units(p: Principal) -> list[dict]:
    """Plan 8 MVP-10.1: the org units the page's org select lists, depth first with their depth: the whole tree for an
    account that sees every tenant, else the subtrees of its own tenant and of the units granted to it."""
    units = policy.org_units(p.ctx)
    a = p.account
    roots = [u.id for u in units.values() if u.parent_id is None or u.parent_id not in units]
    if policy.policy(a).get("tenantScoped"):
        roots = [r for r in (a.tenant, *(p.ctx or policy.Context()).grants.get(a.id, [])) if r and r in units]
    kids: dict[str, list[str]] = {}
    for u in units.values():
        kids.setdefault(u.parent_id or "", []).append(u.id)
    out: list[dict] = []

    def walk(uid: str, depth: int) -> None:
        if any(x["id"] == uid for x in out):
            return
        u = units[uid]
        out.append({"id": u.id, "name": u.name, "kind": u.kind, "depth": depth})
        for k in kids.get(uid, []):
            walk(k, depth + 1)

    for r in roots:
        walk(r, 0)
    return out


def page(
    p: Principal,
    session: Session,
    tenant: str = "",
    cls: str = "",
    route: str = "",
    from_: int = 0,
    to: int = 11,
    model: str = "",
    tenant_filter: str = "All",
    org: str = "",
) -> dict:
    """GET /api/screens/analytics: the rows in the filters, their metrics, the model versions' stats, telemetry, and
    (plan 8 MVP-10.1) the org units the account may pick; `org` narrows everything to the cases of that unit's subtree
    (a unit that does not exist: none). Without `org` the answer is the demo's."""
    ctx = call_ctx(p, session)
    within = orgs.subtree(policy.org_units(p.ctx), org) if org else None
    rows = [
        r
        for r in visible_rows(ctx, tenant_filter)
        if (not tenant or r["tenant"] == tenant)
        and (not cls or r["cls"] == cls)
        and (not route or r["route"] == route)
        and from_ <= r["mi"] <= to
        and (not model or r["model"] == model)
        and (within is None or r["tenant"] in within)
    ]
    live = sum(
        1
        for c in visible_cases(ctx, tenant_filter)
        if c["stage"] == "awaiting_approval" and (within is None or c["owner"] in within)
    )
    return {
        "rows": rows,
        "metrics": metrics(rows, live),
        "model_stats": [model_stats(m["v"]) for m in MODELS],
        "telemetry_unavailable": telemetry_unavailable(session),
        "orgs": actor_units(p),
    }


# ---------------------------------------------------------------- Contract renewals (plan 9, P9-5.7)
RENEWAL_CAVEAT = (
    "Contracts that got a proposal may differ from those that did not (for example larger or better accounts). "
    "This comparison is observational; a 20% region publish is the proof."
)
RENEWAL_BASIS = (
    "observed in the fleet contract system's ended contracts and in refresh cases that recorded an outcome (not modelled)"
)


def _rate(rows: list[Any]) -> dict[str, Any]:
    renewed = sum(1 for r in rows if r.renewed)
    return {"n": len(rows), "renewed": renewed, "rate": renewed / len(rows) if rows else None}


def _compared(rows: list[Any]) -> dict[str, Any]:
    """What the proposals predicted against what happened, over the recorded cases that had a proposal: the mean predicted renewal
    likelihood against the share that renewed, the mean difference of the fee a month after renewal from the fee proposed (percent
    of the proposed fee, over the renewed ones), and the swaps accepted."""
    cs = [r for r in rows if r.source == "case" and r.had_proposal and r.predicted_likelihood is not None]
    fees = [(r.fee_after - r.predicted_fee) / r.predicted_fee * 100 for r in cs if r.renewed and r.fee_after and r.predicted_fee]
    return {
        "n": len(cs),
        "predicted_rate": sum(r.predicted_likelihood or 0 for r in cs) / len(cs) if cs else None,
        "actual_rate": sum(1 for r in cs if r.renewed) / len(cs) if cs else None,
        "fee_error_pct": sum(fees) / len(fees) if fees else None,
        "swaps_accepted": sum(r.swaps_accepted for r in cs),
    }


def renewals(session: Session, p: Principal, since: date, until: date) -> dict[str, Any]:
    """GET /api/screens/analytics/renewals?since=&until=: the renewal rate with and without a proposal, overall and per market and
    size band (counts with each rate; None where a group is empty), what the proposals predicted against what happened, and the
    caveat verbatim. Over the ended contracts and the recorded refresh cases in the account's org units (the tenant boundary)."""
    units = policy.org_units(p.ctx)
    mine = [u for u in units if policy.tenant_ok(p.account, u, p.ctx)]
    if not policy.policy(p.account).get("tenantScoped"):
        mine.append(renewals_repo.WORKSPACE)  # a fleet source bound to no unit is the group's: accounts that see every tenant
    rows = renewals_repo.outcomes(session, mine, since, until)
    segments = []
    for market, size in sorted({(r.market, r.size_band) for r in rows}):
        seg = [r for r in rows if (r.market, r.size_band) == (market, size)]
        segments.append(
            {"market": market, "size": size, "with_proposal": _rate([r for r in seg if r.had_proposal]),
             "without_proposal": _rate([r for r in seg if not r.had_proposal])}
        )  # fmt: skip
    return {
        "since": since.isoformat(), "until": until.isoformat(), "basis": RENEWAL_BASIS, "caveat": RENEWAL_CAVEAT,
        "with_proposal": _rate([r for r in rows if r.had_proposal]),
        "without_proposal": _rate([r for r in rows if not r.had_proposal]),
        "segments": segments, "compared": _compared(rows),
    }  # fmt: skip


# ---------------------------------------------------------------- the Packs tab (plan 9, P9-1.13)
def pack_cases(ctx: CallContext, pack: Pack) -> list[dict[str, Any]]:
    """The live cases of the pack the account may see (a case without a template is the industrial demo's)."""
    return [c for c in visible_cases(ctx) if (c.get("template") or "industrial") == pack.key]


def pack_view(session: Session, p: Principal, key: str = "") -> dict[str, Any]:
    """GET /api/screens/analytics/pack: the pack's KPIs and questions computed from its data over the cases of that pack the
    account may see. KeyError for a pack that is neither a file nor published (the route answers 404)."""
    ctx = call_ctx(p, session)
    keys = sorted({*pack_keys(), *published_keys(session)}, key=lambda k: (k != "industrial", k))  # the primary pack first
    packs = {k: active_pack(session, k, None) for k in keys}
    if not key:  # the first pack with KPIs and cases the account sees, else the primary pack (industrial: the demo's)
        key = next((k for k, v in packs.items() if v.kpis and pack_cases(ctx, v)), keys[0])
    pack = packs[key]
    cases = pack_cases(ctx, pack)
    return {
        "key": key,
        "name": pack.name,
        "cases": len(cases),
        "worked_questions": worked_questions(key),
        "renewals": key == "tool_fleet",  # contract refresh is the tool fleet's
        "packs": [{"key": k, "name": v.name} for k, v in packs.items()],
        "kpis": kpis.kpi_rows(pack, cases),
        "questions": kpis.question_rows(pack, cases),
        "suggestion_rules": list(pack.runtime.suggestion_rules),
        "stages": [{"key": s.key, "label": s.label, "agent": s.agent, "autonomy": s.autonomy} for s in pack.stages],
    }

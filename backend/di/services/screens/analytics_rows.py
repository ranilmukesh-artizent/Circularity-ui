"""Analytics "View data" (plan 11, writer G1): the rows behind a chart, and behind a clicked part of it.

    GET /api/screens/analytics/rows?source=decisions|cases&chart=&key=&<the page's filters>&sort=&dir=&q=&limit=&offset=
        title, subtitle     the chart's title (and the clicked part), "1,277 rows · Oct 25 to Sep 26 · Customer A, Customer B"
        columns             [{key, label, kind, unit?}] in plain words; the table shows exactly these
        rows                one dict per row, keyed by column key (money and numbers as numbers, dates as YYYY-MM-DD)
        total, of, shown    rows after the search box, rows before it (the figure's count), rows in this page
        period, tenants     the months of the page's filter; the tenants the rows belong to
        totals              the money columns added over `total` rows
        sum                 {label, value, unit, n}: the figure the selection adds up to, before the search box
        truncated, can_export   more rows than one export holds (5,000); whether the account may export these rows
    GET /api/screens/analytics/rows.csv?<the same>   the CSV of the same rows (no paging, 5,000 at most, the shown columns
                              only). Written to the journal first: it runs the action `analytics.export` (below).
    POST /api/actions/analytics.export {source, chart, key, ...}   journals the export (who, which chart and part, filters, how
                              many rows); a person only (an agent is refused). The CSV itself is built by the rows.csv endpoint.

Access is the page's own, repeated here, never a second path: `require_page("analytics", <section of the chart>)`, then the
page's rows (`di.services.screens.analytics.page`: the tenant boundary, the top bar's tenant filter, the org subtree and the
page's filters, over `visible_rows`) for closed decisions, and `visible_cases` (tenant boundary AND warehouse lock, the org
subtree) for live cases. The caller never names a column, a table or a filter: `chart` and `key` select a server-side
predicate and a fixed column list. An unknown chart, key part, sort column or source is a 422.

The charts, by `source`. A key is `all`, a token of the chart, or parts joined by `|` of `dim:value` (each dim at most once).
Each line: chart (section) keys -> the figure `sum` adds up to.

decisions
    kpi (waterfall)        all, avoided, pending                      -> uplift; avoided spend; pending count
    waterfall (waterfall)  all, baseline, circularity, route:<id>     -> uplift; baseline; actual; uplift of a route
    pipeline (pipeline)    all (= approved), carried_out, reconciled  -> decisions counted
    mix (mix)              all, route:<id>, month:<0-11>, both        -> decisions carried out
    flow (pipeline)        all, cls:<id>, route:<id>, status:<s>, any -> decisions
    heatmap (mix)          all, route:<id>, cls:<id>, both            -> median uplift per case
    trend (waterfall)      all, month:<0-11>                          -> net recovered (sum of actuals)
    predicted (predicted)  all, model:<v>                             -> decisions counted
    models (models)        all, model:<v>                             -> decisions counted (your rows)
    overrides (overrides)  all, reason:<text>                         -> net effect vs the recommended route
    eng (eng)              all, equip:<model>, comp:<name>, both      -> value lost
    sustain (sustain)      all (= estimated), estimated, measured, route:<id>  -> CO2e kg, estimated or measured
cases
    age (pipeline)         all, band:<0-7|8-14|15-30|30+>, route:<id>, both  -> forecast value of the open decisions
    pack (waterfall)       pack:<key>, then route:<id>, grade:<g>, state:<closed|open|live>  -> net (modelled)

`kpi`, `waterfall`, `pipeline`, `mix` and `predicted` keys are exactly what the page's `drills` and bars open in the browser;
`flow`, `heatmap`, `trend` and `age` are the new charts' parts. `pack` takes `days` (cases opened in the last N days; 0: all) as
the pack headline does. The page's own filters (tenant, cls, route, from, to, model, org) narrow the decisions' rows as they
narrow the charts, so the rows are the rows the figure counts.

Pack cases return a fixed whitelist of columns (id, received, grade, route or channel, status, days, net, CO2e avoided with its
factor set), never the case document. The free-text override reason is shown in the table cut at 200 characters and is never
exported. Net and carbon on cases are modelled or estimated, not realised; the carbon factors are samples (a real set needs
review by Kinective's Legal team before any report).
"""

import csv
import io
from collections.abc import Callable, Collection, Iterator, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from functools import cache
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from di.core import clock, orgs, policy
from di.core.auth import Principal
from di.core.errors import ApiError
from di.repositories import case_times
from di.repositories.common import stage_label
from di.repositories.constants import MODELS, ROUTES
from di.repositories.context import call_ctx, visible_cases
from di.repositories.decisions import median
from di.repositories.packs import active_pack, published_keys
from di.repositories.reference import lists
from di.services.actions.pipeline import CallContext
from di.services.actions.registry import ACTIONS, ActionDef, ActionError, guard, implement
from di.services.modeler.pack import pack_keys
from di.services.questions import HEADLINES
from di.services.questions.headline import NO_GRADE, received_at, route_of
from di.services.screens import analytics as analytics_svc

EXPORT_CAP = 5000  # rows in one export
MAX_LIMIT = 200  # rows in one page of the table
REASON_CHARS = 200  # the override reason is cut here in the table, and never exported

Rec = dict[str, Any]
Pred = Callable[[Rec], bool]
SOURCES = ("decisions", "cases")
STATUS = {"reconciled": "Reconciled", "pending": "Pending", "cancelled": "Demand cancelled", "expired": "Offer expired"}
BANDS = (("0-7", "0 to 7 days", 7), ("8-14", "8 to 14 days", 14), ("15-30", "15 to 30 days", 30), ("30+", "Over 30 days", None))
LIVE = ("approved", "executing")


def bad(message: str) -> ApiError:
    return ApiError("validation_error", message, 422)


# ---------------------------------------------------------------- reference words
@cache
def _months() -> list[str]:
    out: list[str] = lists()["MONTHS"]
    return out


@cache
def _route_names() -> dict[str, str]:
    return {r["id"]: r["name"] for r in ROUTES}


@cache
def _class_labels() -> dict[str, str]:
    return {k: v["label"] for k, v in lists()["CLASSES"].items()}


def row_count(n: int) -> str:
    """ "1 row", "2 rows", "1,277 rows": the count with its noun in the right number."""
    return f"{n:,} {'row' if n == 1 else 'rows'}"


def channel_of(rid: str) -> str:
    """The route a pack proposes, without the request or lot a valuer adds to its id (`rerent:REQ-1` is `rerent`)."""
    return rid.partition(":")[0]


def _route_name(rid: str, extra: dict[str, str] | None = None) -> str:
    """The plain name of a route id: the pack's own name, else the reference list's, of the id and then of its channel."""
    for k in (rid, channel_of(rid)):
        if name := (extra or {}).get(k) or _route_names().get(k):
            return name
    return rid


# ---------------------------------------------------------------- columns
@dataclass(frozen=True)
class Col:
    key: str
    label: str
    kind: str
    get: Callable[[Rec], Any]
    unit: str | None = None
    sort: Callable[[Rec], Any] | None = None  # the value the column sorts by, when it is not what it shows
    total: bool = False  # a money column added in `totals`
    export: bool = True  # False: shown in the table, never exported
    limit: int | None = None  # text cut to this many characters in the table


def _month_label(r: Rec) -> str:
    return _months()[r["mi"]]


def _vs(r: Rec) -> float | None:
    return r["actual"] - r["baseline"] if r["status"] == "reconciled" and r["actual"] is not None else None


def _ov(field_: str) -> Callable[[Rec], Any]:
    return lambda r: (r["override"] or {}).get(field_)


def _usd(key: str, label: str, get: Callable[[Rec], Any], total: bool = True) -> Col:
    return Col(key, label, "money", get, "usd", total=total)


DEC: dict[str, Col] = {
    c.key: c
    for c in (
        Col("id", "Case", "text", lambda r: r["id"]),
        Col("month", "Month", "text", _month_label, sort=lambda r: r["mi"]),
        Col("tenant", "Tenant", "text", lambda r: r["tenant"]),
        Col("cls", "Asset class", "text", lambda r: _class_labels().get(r["cls"], r["cls"])),
        Col("route", "Route", "text", lambda r: _route_name(r["route"])),
        Col("status", "Status", "text", lambda r: STATUS.get(r["status"], r["status"])),
        Col("model", "Model", "text", lambda r: r["model"]),
        Col("asset", "Asset", "text", lambda r: r["assetId"]),
        _usd("p10", "Predicted P10", lambda r: r["p10"], total=False),
        _usd("p50", "Predicted P50", lambda r: r["p50"]),
        _usd("p90", "Predicted P90", lambda r: r["p90"], total=False),
        _usd("actual", "Actual", lambda r: r["actual"]),
        _usd("baseline", "Baseline (modelled)", lambda r: r["baseline"]),
        _usd("vs", "Vs baseline", _vs),
        Col("days", "Days to realise", "days", lambda r: r["days"]),
        _usd("avoided", "Avoided spend", lambda r: r["avoided"]),
        Col("co2e", "CO2e estimated", "number", lambda r: r["co2e"], "kg"),
        Col("co2m", "CO2e measured", "number", lambda r: r["co2m"], "kg"),
        Col("rec", "Recommended route", "text", lambda r: _route_name(_ov("rec")(r) or "")),
        Col("exec", "Carried-out route", "text", lambda r: _route_name(_ov("exec")(r) or "")),
        _usd("ovr", "Estimated vs recommended", _ov("delta")),
        Col("reason", "Override reason", "text", _ov("reason"), export=False, limit=REASON_CHARS),
        Col("equip", "Equipment model", "text", lambda r: r["equip"]),
        Col("comp", "Component", "text", lambda r: r["comp"]),
        _usd("ero", "Value lost", lambda r: r["ero"]),
    )
}
BASE = (
    "id",
    "month",
    "tenant",
    "cls",
    "route",
    "status",
    "model",
    "asset",
    "p50",
    "actual",
    "baseline",
    "vs",
    "days",
    "avoided",
    "co2e",
    "co2m",
)
COLS: dict[str, tuple[str, ...]] = {
    "predicted": ("id", "month", "tenant", "cls", "route", "model", "asset", "p10", "p50", "p90", "actual", "vs"),
    "overrides": ("id", "month", "tenant", "cls", "asset", "rec", "exec", "ovr", "reason", "actual", "baseline", "vs"),
    "eng": ("id", "month", "tenant", "cls", "route", "asset", "equip", "comp", "ero", "actual", "baseline", "vs"),
    "sustain": ("id", "month", "tenant", "cls", "route", "status", "asset", "co2e", "co2m"),
}


def _date(v: datetime | None) -> str | None:
    return v.date().isoformat() if v else None


CASE: dict[str, Col] = {
    c.key: c
    for c in (
        Col("id", "Case", "text", lambda r: r["id"]),
        Col("tenant", "Tenant", "text", lambda r: r["tenant"]),
        Col("received", "Received", "date", lambda r: _date(r["received"]), sort=lambda r: r["received"]),
        Col("grade", "Grade", "text", lambda r: r["grade"]),
        Col("route", "Route", "text", lambda r: r["route_name"]),
        Col("status", "Status", "text", lambda r: r["status"]),
        Col("days", "Days", "days", lambda r: r["days"]),
        Col("net", "Net (modelled)", "money", lambda r: r["net"], "usd", total=True),
        Col("co2", "CO2e avoided (estimated)", "number", lambda r: r["co2"], "kg"),
        Col("co2_set", "Carbon factor set", "text", lambda r: r["co2_set"]),
    )
}
AGE_COLS = ("id", "tenant", "received", "days", "route", "net")
PACK_COLS = ("id", "received", "grade", "route", "status", "days", "net", "co2", "co2_set")


# ---------------------------------------------------------------- charts
@dataclass(frozen=True)
class SumSpec:
    label: str
    unit: str  # usd, count or kg
    fn: Callable[[list[Rec]], float]


@dataclass(frozen=True)
class Res:
    """What a key selects: the title, the predicate over the loaded records and the figure the selection adds up to."""

    title: str
    pred: Pred
    sum: SumSpec
    labels: tuple[str, ...] = ()


@dataclass(frozen=True)
class Filters:
    """The page's own filters (analytics.page), and the pack headline's period."""

    tenant: str = ""
    cls: str = ""
    route: str = ""
    from_: int = 0
    to: int = 11
    model: str = ""
    tenant_filter: str = "All"
    org: str = ""
    days: int = 0


def _zero(r: Rec) -> int:  # noqa: ARG001 - the order of a chart that names none
    return 0


def _every(r: Rec) -> bool:  # noqa: ARG001
    return True


@dataclass(frozen=True)
class Chart:
    id: str
    source: str
    section: str | None  # the analytics section that shows the chart (None: the page)
    title: str
    dims: tuple[str, ...]
    tokens: tuple[str, ...]
    resolve: Callable[[str, dict[str, str], list[Rec]], Res]
    columns: tuple[Col, ...]
    note: str = ""
    default_sort: Callable[[Rec], Any] = field(default=_zero)


def _is(get: Callable[[Rec], Any], v: Any) -> Pred:
    return lambda r: get(r) == v


def _state(v: str) -> Pred:
    if v == "closed":
        return lambda r: r["stage"] == "closed"
    if v == "open":
        return lambda r: r["stage"] != "closed"
    return lambda r: r["stage"] in LIVE


def _count(rows: list[Rec]) -> float:
    return len(rows)


def _total(fn: Callable[[Rec], float | None]) -> Callable[[list[Rec]], float]:
    return lambda rows: sum(fn(r) or 0 for r in rows)


COUNT = SumSpec("Decisions", "count", _count)
UPLIFT = SumSpec("Recovered vs baseline", "usd", _total(lambda r: (r["actual"] or 0) - r["baseline"]))
RC: Pred = lambda r: r["status"] == "reconciled"  # noqa: E731
CARRIED: Pred = lambda r: r["status"] in ("reconciled", "pending")  # noqa: E731
MEASURED: Pred = lambda r: r["status"] == "reconciled" and r["co2m"] is not None  # noqa: E731


def _getters() -> dict[str, Callable[[Rec], str | None]]:
    return {
        "route": lambda r: r["route"],
        "cls": lambda r: r["cls"],
        "status": lambda r: r["status"],
        "month": lambda r: str(r["mi"]),
        "model": lambda r: r["model"],
        "equip": lambda r: r["equip"],
        "comp": lambda r: r["comp"],
        "reason": lambda r: (r["override"] or {}).get("reason"),
    }


def _allowed(rows: list[Rec]) -> dict[str, Collection[str]]:
    ref = lists()
    return {
        "route": set(_route_names()),
        "cls": set(ref["CLASSES"]) | {r["cls"] for r in rows},
        "status": set(STATUS),
        "month": {str(i) for i in range(len(_months()))},
        "model": {m["v"] for m in MODELS},
        "equip": {e["m"] for e in ref["EQUIP"]},
        "comp": set(ref["COMPS"]),
        # the reasons of the rows the account sees (a reason that only others' rows hold is unknown to it)
        "reason": {str(r["override"]["reason"]) for r in rows if r["override"]},
    }


def _label(dim: str, v: str) -> str:
    return {
        "route": _route_name(v),
        "cls": _class_labels().get(v, v),
        "status": STATUS.get(v, v),
        "month": _months()[int(v)] if v.isdigit() and int(v) < len(_months()) else v,
    }.get(dim, v)


def _dims(raw: dict[str, str], rows: list[Rec], base: Pred) -> tuple[Pred, tuple[str, ...]]:
    """The predicate of a key's `dim:value` parts, each value checked against what the dim can hold (422 otherwise)."""
    allowed, get = _allowed(rows), _getters()
    checks: list[tuple[Callable[[Rec], str | None], str]] = []
    for dim, v in raw.items():
        if v not in allowed[dim]:
            raise bad(f"Unknown {dim} {v!r}.")
        checks.append((get[dim], v))
    labels = tuple(_label(d, v) for d, v in raw.items())
    return (lambda r: base(r) and all(g(r) == v for g, v in checks)), labels


def _by_dims(title: str, base: Pred, total: SumSpec) -> Callable[[str, dict[str, str], list[Rec]], Res]:
    def resolve(tok: str, raw: dict[str, str], rows: list[Rec]) -> Res:  # noqa: ARG001 - no tokens
        pred, labels = _dims(raw, rows, base)
        return Res(title, pred, total, labels)

    return resolve


def _kpi(tok: str, raw: dict[str, str], rows: list[Rec]) -> Res:  # noqa: ARG001
    if tok == "avoided":
        return Res(
            "Confirmed avoided spend", lambda r: r["avoided"] > 0, SumSpec("Avoided spend", "usd", _total(lambda r: r["avoided"]))
        )
    if tok == "pending":
        return Res("Pending outcomes", lambda r: r["status"] == "pending", SumSpec("Pending decisions", "count", _count))
    return Res("Additional net recovery vs baseline", RC, UPLIFT)


def _waterfall(tok: str, raw: dict[str, str], rows: list[Rec]) -> Res:
    title = "Recovery waterfall: baseline to Circularity"
    if tok == "baseline":
        return Res(
            title + " · Baseline", RC, SumSpec("Baseline (modelled)", "usd", _total(lambda r: r["baseline"])), ("Baseline",)
        )
    if tok == "circularity":
        return Res(
            title + " · With Circularity", RC, SumSpec("Recovered", "usd", _total(lambda r: r["actual"])), ("With Circularity",)
        )
    pred, labels = _dims(raw, rows, RC)
    return Res(title, pred, UPLIFT, labels)


def _pipeline(tok: str, raw: dict[str, str], rows: list[Rec]) -> Res:  # noqa: ARG001
    if tok == "carried_out":
        return Res("Decisions carried out", CARRIED, COUNT)
    if tok == "reconciled":
        return Res("Reconciled decisions", RC, COUNT)
    return Res("Approved decisions", _every, COUNT)


def _heatmap(tok: str, raw: dict[str, str], rows: list[Rec]) -> Res:  # noqa: ARG001
    pred, labels = _dims(raw, rows, RC)
    spec = SumSpec("Median uplift per case", "usd", lambda rs: median([(r["actual"] or 0) - r["baseline"] for r in rs]))
    return Res("Median uplift by route and asset class", pred, spec, labels)


def _models(tok: str, raw: dict[str, str], rows: list[Rec]) -> Res:  # noqa: ARG001
    pred, labels = _dims(raw, rows, lambda r: r["status"] == "reconciled" and r["route"] != "exit" and not r["override"])
    return Res("Model versions: the learning loop", pred, COUNT, labels)


def _predicted(tok: str, raw: dict[str, str], rows: list[Rec]) -> Res:  # noqa: ARG001
    def point(r: Rec) -> bool:
        return (
            r["status"] == "reconciled" and r["route"] != "exit" and r["p50"] > 0 and (r["actual"] or 0) > 0 and not r["override"]
        )

    pred, labels = _dims(raw, rows, point)
    return Res("Predicted vs actual", pred, COUNT, labels)


def _sustain(tok: str, raw: dict[str, str], rows: list[Rec]) -> Res:
    est = SumSpec("CO2e avoided, estimated", "kg", _total(lambda r: r["co2e"]))
    meas = SumSpec("CO2e avoided, measured", "kg", _total(lambda r: r["co2m"]))
    if tok == "measured":
        return Res("Sustainability · Measured", MEASURED, meas, ("Measured",))
    if tok == "estimated" or not raw:
        return Res("Sustainability", RC, est)
    pred, labels = _dims(raw, rows, MEASURED)  # a route bar compares estimated with measured on the cases that have both
    return Res("Sustainability", pred, meas, labels)


def _decision_chart(
    cid: str,
    section: str,
    title: str,
    dims: tuple[str, ...],
    tokens: tuple[str, ...],
    resolve: Callable[..., Res],
    note: str = "",
) -> Chart:
    keys = COLS.get(cid, BASE)
    return Chart(
        cid, "decisions", section, title, dims, tokens, resolve, tuple(DEC[k] for k in keys), note,
        default_sort=lambda r: -abs(r["actual"] or r["p50"]),
    )  # fmt: skip


# ---------------------------------------------------------------- live cases
def _received(c: Rec, opened: datetime | None) -> datetime | None:
    """When the asset was received (the case's own date), else when the case opened: `days` counts from it."""
    return received_at(c, opened)


def band_of(days: int) -> str:
    return next(k for k, _, hi in BANDS if hi is None or days <= hi)


def _number(v: Any) -> float | None:
    return float(v) if isinstance(v, int | float) and not isinstance(v, bool) else None


def _rec_of(c: Rec, opened: datetime | None, closed: datetime | None, now: datetime, names: dict[str, str]) -> Rec:
    """One live case as the cases' tables show it: only the whitelisted fields, never the case document."""
    got = _received(c, opened)
    route = route_of(c)
    stage = str(c.get("stage"))
    end = closed if stage == "closed" and closed else now
    secs = (end - got).total_seconds() if got else 0.0
    prov = route.get("co2Prov") if route else None
    return {
        "id": c["id"],
        "tenant": c["owner"],
        "received": got,
        "grade": str(c.get("grade") or NO_GRADE),
        "route_id": channel_of(str(route["id"])) if route else None,
        "route_name": _route_name(str(route["id"]), names) if route else "No route yet",
        "stage": stage,
        "status": "Closed" if stage == "closed" else stage_label(c),
        "days": round(max(secs, 0.0) / 86400, 1),
        "age": int(max(secs, 0.0) // 86400),
        "net": _number(route.get("net")) if route else None,
        "co2": _number(route.get("co2")) if route else None,
        "co2_set": str(prov["set"]) if isinstance(prov, dict) and prov.get("set") else None,
    }


def _names_for(session: Session, cases: Sequence[Rec]) -> dict[str, str]:
    """Route names of the packs the cases use (a case without a template is the demo's, named in the reference list)."""
    out: dict[str, str] = {}
    for key in sorted({c.get("template") or "industrial" for c in cases}):
        try:
            out |= {r.id: r.name for r in active_pack(session, key, None).routes}
        except KeyError:
            continue
    return out


def open_cases(session: Session, p: Principal, f: Filters) -> list[Rec]:
    """The live cases awaiting approval the account may see (tenant boundary, warehouse lock, top bar filter, org subtree):
    the page's `liveOpen` KPI counts exactly these."""
    ctx = call_ctx(p, session)
    within = orgs.subtree(policy.org_units(p.ctx), f.org) if f.org else None
    return [
        c
        for c in visible_cases(ctx, f.tenant_filter)
        if c["stage"] == "awaiting_approval" and (within is None or c["owner"] in within)
    ]


def age_records(session: Session, p: Principal, f: Filters) -> list[Rec]:
    cases = open_cases(session, p, f)
    times = case_times.times(session, [c["id"] for c in cases])
    names, now = _names_for(session, cases), clock.now()
    return [_rec_of(c, t.opened if (t := times.get(c["id"])) else None, None, now, names) for c in cases]


def _age_resolve(tok: str, raw: dict[str, str], rows: list[Rec]) -> Res:  # noqa: ARG001
    bands = {k for k, _, _ in BANDS}
    routes = {r["route_id"] for r in rows if r["route_id"]} | set(_route_names())
    checks: list[Pred] = []
    labels: list[str] = []
    for dim, v in raw.items():
        if dim == "band":
            if v not in bands:
                raise bad(f"Unknown band {v!r}.")
            checks.append(_is(lambda r: band_of(r["age"]), v))
            labels.append(next(lbl for k, lbl, _ in BANDS if k == v))
        else:
            if v not in routes:
                raise bad(f"Unknown route {v!r}.")
            checks.append(_is(lambda r: r["route_id"], v))
            labels.append(next((r["route_name"] for r in rows if r["route_id"] == v), _route_name(v)))
    spec = SumSpec("Value at risk (forecast, modelled)", "usd", _total(lambda r: r["net"]))
    return Res("Open decisions by age", lambda r: all(c(r) for c in checks), spec, tuple(labels))


def _pack_resolve(tok: str, raw: dict[str, str], rows: list[Rec]) -> Res:  # noqa: ARG001
    grades = {r["grade"] for r in rows}
    routes = {r["route_id"] for r in rows if r["route_id"]}
    checks: list[Pred] = []
    labels: list[str] = []
    for dim, v in raw.items():
        if dim == "pack":
            continue
        if dim == "state":
            if v not in ("closed", "open", "live"):
                raise bad(f"Unknown state {v!r}.")
            checks.append(_state(v))
            labels.append({"closed": "Closed", "open": "Not closed", "live": "Live (approved or executing)"}[v])
        elif dim == "grade":
            if v not in grades and v != NO_GRADE:
                raise bad(f"Unknown grade {v!r}.")
            checks.append(_is(lambda r: r["grade"], v))
            labels.append("Grade " + v)
        else:
            if v not in routes:
                raise bad(f"Unknown route {v!r}.")
            checks.append(_is(lambda r: r["route_id"], v))
            labels.append(next(r["route_name"] for r in rows if r["route_id"] == v))
    spec = SumSpec("Net (modelled)", "usd", _total(lambda r: r["net"]))
    title = f"{rows[0]['pack_name']} cases" if rows else "Pack cases"
    return Res(title, lambda r: all(c(r) for c in checks), spec, tuple(labels))


def _pack_records(session: Session, p: Principal, f: Filters, pack_key: str) -> list[Rec]:
    """The cases of one pack the account may see, as whitelisted records (the Packs tab's and the headline's own set: its
    cases ignore the top bar's tenant filter and the org select), opened in the last `days` days when `days` is given."""
    if pack_key not in {*pack_keys(), *published_keys(session)}:
        raise bad(f"Unknown pack {pack_key!r}.")
    pack = active_pack(session, pack_key, None)
    ctx = call_ctx(p, session)
    cases = analytics_svc.pack_cases(ctx, pack)
    times = case_times.times(session, [c["id"] for c in cases])
    names, now = {r.id: r.name for r in pack.routes}, clock.now()
    recs = []
    for c in cases:
        t = times.get(c["id"])
        if f.days and (t is None or (now - t.opened).total_seconds() > f.days * 86400):
            continue
        recs.append(_rec_of(c, t.opened if t else None, t.closed if t else None, now, names) | {"pack_name": pack.name})
    return recs


# ---------------------------------------------------------------- the registry
CHARTS: dict[str, Chart] = {}


def _reg(c: Chart) -> None:
    CHARTS[c.id] = c


for _c in (
    _decision_chart("kpi", "waterfall", "Additional net recovery vs baseline", (), ("avoided", "pending"), _kpi),
    _decision_chart(
        "waterfall",
        "waterfall",
        "Recovery waterfall: baseline to Circularity",
        ("route",),
        ("baseline", "circularity"),
        _waterfall,
    ),
    _decision_chart(
        "pipeline", "pipeline", "Pipeline: case to reconciled", (), ("approved", "carried_out", "reconciled"), _pipeline
    ),
    _decision_chart("mix", "mix", "Route mix over time", ("route", "month"), (), _by_dims("Route mix over time", CARRIED, COUNT)),
    _decision_chart(
        "flow",
        "pipeline",
        "Where decisions go: class, route, status",
        ("cls", "route", "status"),
        (),
        _by_dims("Where decisions go: class, route, status", _every, COUNT),
    ),  # fmt: skip
    _decision_chart("heatmap", "mix", "Median uplift by route and asset class", ("route", "cls"), (), _heatmap),
    _decision_chart(
        "trend",
        "waterfall",
        "Net recovered per month",
        ("month",),
        (),
        _by_dims("Net recovered per month", RC, SumSpec("Net recovered", "usd", _total(lambda r: r["actual"]))),
    ),  # fmt: skip
    _decision_chart(
        "predicted",
        "predicted",
        "Predicted vs actual",
        ("model",),
        (),
        _predicted,
        "overrides, exit routes and pending cases are not points on the chart",
    ),  # fmt: skip
    _decision_chart("models", "models", "Model versions: the learning loop", ("model",), (), _models, "your rows"),
    _decision_chart(
        "overrides",
        "overrides",
        "Overrides",
        ("reason",),
        (),
        _by_dims(
            "Overrides",
            lambda r: r["status"] == "reconciled" and bool(r["override"]),
            SumSpec("Net effect vs recommended route (estimated)", "usd", _total(lambda r: r["override"]["delta"])),
        ),
    ),  # fmt: skip
    _decision_chart(
        "eng",
        "eng",
        "Engineering economic intelligence",
        ("equip", "comp"),
        (),
        _by_dims(
            "Engineering economic intelligence", lambda r: r["ero"] > 0, SumSpec("Value lost", "usd", _total(lambda r: r["ero"]))
        ),
    ),  # fmt: skip
    _decision_chart(
        "sustain",
        "sustain",
        "Sustainability",
        ("route",),
        ("estimated", "measured"),
        _sustain,
        "CO2e figures are estimates from sample factors (synthetic) or measured values; never mixed",
    ),  # fmt: skip
    Chart(
        "age",
        "cases",
        "pipeline",
        "Open decisions by age",
        ("band", "route"),
        (),
        _age_resolve,
        tuple(CASE[k] for k in AGE_COLS),
        "forecast values are modelled, not realised",
        default_sort=lambda r: -(r["age"]),
    ),  # fmt: skip
    Chart(
        "pack",
        "cases",
        "waterfall",  # the headline's own section: the one a role needs to see the pack tiles
        "Pack cases",
        ("pack", "route", "grade", "state"),
        (),
        _pack_resolve,
        tuple(CASE[k] for k in PACK_COLS),
        "net is modelled and carbon estimated from sample factors, not realised",
        default_sort=lambda r: -(r["net"] or 0),
    ),  # fmt: skip
):
    _reg(_c)


def charts() -> dict[str, list[str]]:
    """chart id -> its tokens and dims, for documentation and tests."""
    return {c.id: [*c.tokens, *(d + ":" for d in c.dims)] for c in CHARTS.values()}


def parse_key(chart: Chart, key: str) -> tuple[str, dict[str, str]]:
    """(tok, dims) of a key: `all`, one of the chart's tokens, or `dim:value` parts joined by `|` (422 for anything else)."""
    key = key.strip()
    if key in ("", "all"):
        key = "all"
        return "all", {}
    if key in chart.tokens:
        return key, {}
    raw: dict[str, str] = {}
    for part in key.split("|"):
        dim, sep, v = part.partition(":")
        if not sep or dim not in chart.dims or dim in raw or not v:
            raise bad(f"Unknown key {key!r} for the chart {chart.id}.")
        raw[dim] = v
    return "", raw


# ---------------------------------------------------------------- the selection
@dataclass
class Selection:
    chart: Chart
    res: Res
    recs: list[Rec]  # the selection, before the search box
    matched: list[Rec]  # after the search box, in the requested order
    columns: list[Col]
    period: str
    tenants: list[str]


def _norm(s: str) -> str:
    return s.casefold()


def _matches(chart: Chart, r: Rec, q: str) -> bool:
    fields = ("id", "model", "assetId", "site") if chart.source == "decisions" else ("id", "route_name", "grade", "tenant")
    return any(q in _norm(str(r.get(k) or "")) for k in fields)


def _ordered(recs: list[Rec], col: Col | None, chart: Chart, desc: bool) -> list[Rec]:
    """Stable: ties keep the id order; empty values go last either way. No column: the chart's own order."""
    base = sorted(recs, key=lambda r: str(r["id"]))
    if col is None:
        return sorted(base, key=chart.default_sort)
    key = col.sort or col.get

    def k(r: Rec) -> Any:
        v = key(r)
        return _norm(v) if isinstance(v, str) else v

    have = [r for r in base if key(r) is not None]
    return sorted(have, key=k, reverse=desc) + [r for r in base if key(r) is None]


def select(
    session: Session,
    p: Principal,
    source: str,
    chart_id: str,
    key: str,
    f: Filters,
    sort: str = "",
    dir_: str = "desc",
    q: str = "",
) -> Selection:
    chart = CHARTS.get(chart_id)
    if source not in SOURCES:
        raise bad(f"Unknown source {source!r}.")
    if chart is None or chart.source != source:
        raise bad(f"Unknown chart {chart_id!r} for the source {source}.")
    p.require_page("analytics", chart.section)  # the section of the chart: the page's own gate
    tok, raw = parse_key(chart, key)
    if chart.id == "pack":
        if "pack" not in raw:
            raise bad("The chart pack needs a key that names the pack, for example pack:tool_fleet.")
        recs = _pack_records(session, p, f, raw["pack"])
    elif chart.source == "cases":
        recs = age_records(session, p, f)
    else:
        recs = analytics_svc.page(
            p, session, tenant=f.tenant, cls=f.cls, route=f.route, from_=f.from_, to=f.to, model=f.model,
            tenant_filter=f.tenant_filter, org=f.org,
        )["rows"]  # fmt: skip
    res = chart.resolve(tok, raw, recs)
    sel = [r for r in recs if res.pred(r)]
    columns = list(chart.columns)
    if chart.id == "pack" and HEADLINES.get(raw["pack"]) and HEADLINES[raw["pack"]].route_word == "channel":
        columns = [replace(c, label="Channel") if c.key == "route" else c for c in columns]  # a device's route is its channel
    col = None
    if sort:
        col = next((c for c in columns if c.key == sort), None)
        if col is None:
            raise bad(f"Unknown sort column {sort!r}.")
    needle = _norm(q.strip())
    matched = [r for r in sel if not needle or _matches(chart, r, needle)]
    if chart.source == "decisions":
        top = max(0, min(f.from_, len(_months()) - 1)), max(0, min(f.to, len(_months()) - 1))
        period = f"{_months()[top[0]]} to {_months()[top[1]]}"
        tenants = sorted({r["tenant"] for r in sel})
    else:
        period = f"cases opened in the last {f.days} days" if f.days else ("as of " + clock.now().date().isoformat())
        tenants = sorted({r["tenant"] for r in sel})
    return Selection(chart, res, sel, _ordered(matched, col, chart, dir_ != "asc"), columns, period, tenants)


def _cell(c: Col, r: Rec) -> Any:
    v = c.get(r)
    if isinstance(v, str) and c.limit and len(v) > c.limit:
        return v[: c.limit - 1] + "…"
    return v


def rows(
    session: Session, p: Principal, source: str, chart: str, key: str, f: Filters, sort: str = "", dir_: str = "desc",
    q: str = "", limit: int = 50, offset: int = 0,
) -> dict[str, Any]:  # fmt: skip
    """GET /api/screens/analytics/rows (see the module docstring). `limit` is capped at 200."""
    s = select(session, p, source, chart, key, f, sort, dir_, q)
    limit = max(1, min(limit, MAX_LIMIT))
    page = s.matched[max(0, offset) : max(0, offset) + limit]
    total = len(s.matched)
    value = s.res.sum.fn(s.recs)
    labels = " · ".join(s.res.labels)
    note = s.chart.note if s.chart.note else ""
    parts = [row_count(len(s.recs)), s.period, ", ".join(s.tenants) or "no tenant"] + ([note] if note else [])
    return {
        "title": s.res.title if not labels or labels in s.res.title else f"{s.res.title} · {labels}",
        "subtitle": " · ".join(parts),
        "columns": [{"key": c.key, "label": c.label, "kind": c.kind} | ({"unit": c.unit} if c.unit else {}) for c in s.columns],
        "rows": [{c.key: _cell(c, r) for c in s.columns} for r in page],
        "total": total,
        "of": len(s.recs),
        "shown": len(page),
        "period": s.period,
        "tenants": s.tenants,
        "totals": {c.key: sum(c.get(r) or 0 for r in s.matched) for c in s.columns if c.total},
        "sum": {"label": s.res.sum.label, "value": value, "unit": s.res.sum.unit, "n": len(s.recs)},
        "truncated": total > EXPORT_CAP,
        "can_export": total > 0 and p.agent_id is None,
    }


# ---------------------------------------------------------------- the export (journaled)
def _safe(v: Any) -> Any:
    """A text cell that a spreadsheet would run as a formula is written as text."""
    return "'" + v if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r") else v


def csv_lines(s: Selection) -> Iterator[str]:
    """The CSV of the selection: the shown columns except those never exported, in the table's order, 5,000 rows at most."""
    cols = [c for c in s.columns if c.export]
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")

    def flush() -> str:
        out = buf.getvalue()
        buf.seek(0)
        buf.truncate()
        return out

    w.writerow([c.label for c in cols])
    yield flush()
    for r in s.matched[:EXPORT_CAP]:
        w.writerow([_safe(c.get(r)) for c in cols])
        yield flush()


def _int(v: Any, default: int) -> int:
    return default if v is None or isinstance(v, bool) or not isinstance(v, int | float) else int(v)


def export_selection(session: Session, p: Principal, params: dict[str, Any]) -> Selection:
    """The selection an export holds, from the same parameters the rows read takes (what the action journals)."""
    f = Filters(
        tenant=str(params.get("tenant") or ""), cls=str(params.get("cls") or ""), route=str(params.get("route") or ""),
        from_=_int(params.get("from"), 0), to=_int(params.get("to"), 11),
        model=str(params.get("model") or ""), tenant_filter=str(params.get("tenant_filter") or "All"),
        org=str(params.get("org") or ""), days=_int(params.get("days"), 0),
    )  # fmt: skip
    return select(
        session, p, str(params["source"]), str(params["chart"]), str(params.get("key") or "all"), f,
        str(params.get("sort") or ""), str(params.get("dir") or "desc"), str(params.get("q") or ""),
    )  # fmt: skip


ACTIONS.setdefault(
    "analytics.export",
    ActionDef(
        id="analytics.export", title="Export the rows behind an analytics chart", verb="export analytics rows", risk="act",
        perm=None, scope="none",
        desc="Record that a person exported the rows behind an Analytics chart (the chart, the part, the filters and how many "
        "rows): the journal entry the rows.csv download is written under. Only for the rows the person already sees; no agent.",
        input={
            "source": {"req": True, "t": "string"}, "chart": {"req": True, "t": "string"}, "key": {"req": False, "t": "string"},
            "tenant": {"req": False, "t": "string"}, "cls": {"req": False, "t": "string"}, "route": {"req": False, "t": "string"},
            "from": {"req": False, "t": "number"}, "to": {"req": False, "t": "number"}, "model": {"req": False, "t": "string"},
            "tenant_filter": {"req": False, "t": "string"}, "org": {"req": False, "t": "string"},
            "days": {"req": False, "t": "number"},
            "sort": {"req": False, "t": "string"}, "dir": {"req": False, "t": "string"}, "q": {"req": False, "t": "string"},
        },
    ),
)  # fmt: skip


@guard("analytics.export")
def _no_agent_export(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:  # noqa: ARG001
    if ctx.preparer:
        return "approval_required", "No agent exports analytics rows: a person does this."
    return None


@implement("analytics.export")
def analytics_export(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    """Check the export is one this person may make (the section's gate, a known chart and key) and say how many rows it holds."""
    acct = ctx.actor.account
    if acct is None:
        raise ActionError("out_of_scope", "Sign in first.")
    p = Principal(account=acct, ctx=ctx.actor.ctx or policy.Context())
    try:
        s = export_selection(ctx.session, p, i)
    except ApiError as e:
        raise ActionError(e.code, e.message) from e
    except HTTPException as e:
        detail: dict[str, Any] = e.detail if isinstance(e.detail, dict) else {}
        raise ActionError(
            str(detail.get("code", "out_of_scope")), str(detail.get("message", "Not available for this view."))
        ) from e
    n = min(len(s.matched), EXPORT_CAP)
    return {
        "rows": n,
        "capped": len(s.matched) > EXPORT_CAP,
        "chart": s.chart.id,
        "columns": [c.key for c in s.columns if c.export],
    }

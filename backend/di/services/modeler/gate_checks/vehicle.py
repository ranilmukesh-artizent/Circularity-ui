"""The used-car compliance gates (plan 9, P9-9.8 title, P9-9.9 odometer and recall; stories UC-06, UC-24, UC-07, UC-08). Pure.
Implements the checks of registry entry I-2 for the catalogue gates `G-VEH-TITLE`, `G-VEH-BRAND` (Compliance, stage match),
`G-VEH-ODO` and `G-VEH-RECALL` (Compliance, stage condition); they run before any business rule (R20).

    check_title_clear(case, pack, gate) -> GateResult    G-VEH-TITLE: clear title, no open finance
    check_title_brand(case, pack, gate) -> GateResult    G-VEH-BRAND: a title brand is disclosed, some brands block retail
    check_odometer(case, pack, gate) -> GateResult       G-VEH-ODO: the odometer photo agrees with the lease record
    check_open_recall(case, pack, gate) -> GateResult    G-VEH-RECALL: no retail with an open recall, a fleet sells none

**G-VEH-TITLE.** The evidence `title_status` is the title and lien search (`di.services.cases.title_evidence`: title status,
whether a lien is open, the trade-in's payoff). The gate passes when the title is `clear`, no lien is open and, for a
trade-in (`return_kind`), the customer's payoff is confirmed. Otherwise every route of `params.routes` (the four sale and
salvage channels) fails, effect `block`, and the case is held until a person has the lien released:
  - no search on file: "Title and lien search not on file", `evidence_missing: ("title_status",)`;
  - title not clear or a lien open: "Clear title, no open finance", `evidence_missing: ("lien_release",)`;
  - trade-in with the payoff not confirmed: "Payoff of the customer's loan not confirmed", `("lien_release",)`.
`gate_hold` raises the exception `EX-UC-LIEN` for the title desk and closes it when the release arrives (the evidence
`lien_release` lands, X-07); `work.resolve` refuses a person's answer while no release is on file. An agent never resolves it
(`work.resolve` is in `FORBIDDEN_ACTIONS`).

**G-VEH-BRAND.** The evidence `title_brand` (the case's `title.brand` triggers the gate). A brand in `params.disclose_brands`
is disclosed: the result's `disclosures` hold "Title brand: <brand>" and the decision puts it on every route
(`gates.apply_disclosures`); a brand in `params.retail_blocked_brands` also fails `retail` with "Title brand <brand>: retail
blocked by pack" (effect `block`); a brand that only needs disclosing has effect `disclose` and passes (no route is excluded).
A brand is not a hold: the case keeps its recommendation among the routes left.

**G-VEH-ODO.** The case fact `odometer` (`di.services.cases.vehicle_evidence`). A car whose model year is before
`params.exempt_model_year_before`, or that is `params.exempt_age_years` old or more, passes: "Odometer disclosure exempt". A lease
return (`return_kind` `lease_end`) with no `statement_ref` fails with effect `require_step` and `evidence_missing:
("odometer_statement",)`, no route excluded. When the inspection's `photo_reading` and the lease system's `lease_record` differ by
more than `params.tolerance_miles` the gate fails with effect `block` on every route of the gate and `hold`: no route is valued
and `gate_hold` raises `EX-UC-ODO` for the inspection lead ("Second inspection before pricing"); a new reading that agrees
releases it (X-07). `not_actual` adds the disclosure "Odometer reading is not the actual mileage" to every route (effect
`disclose` when nothing else fails).

**G-VEH-RECALL.** The case fact `recall` and the evidence `vin_recall`. A check with no date, or older than
`params.check_max_age_days` at the case's `gateNow` (`valuers.fleet_evidence.NOW_KEY`; a case read without it is not judged
stale), fails with effect `require_step` and `evidence_missing: ("recall_check",)`: "Recall check older than 30 days; re-run"
(the action `evidence.refresh` re-runs it). An open recall with no remedy reference is disclosed as "Open recall disclosed:
<campaign ids>" on every route and blocks `retail` ("Open recall: no retail until remedied"); a seller fleet of
`params.rental_fleet_min` or more blocks every route of `params.rental_fleet_block_routes` instead. Neither holds the case.
The check's date is the evidence's `at`.

Never does: read the canonical store, the clock or a session, release a lien, or write a case. State title and brand law differ
and is unconfirmed per state; the pack's lists are data, and any wording built on them needs review by Kinective's Legal team
before it is relied on.
"""

from collections.abc import Mapping
from datetime import timedelta
from typing import Any

from di.services.modeler.evidence import evidence_of, parse_time
from di.services.modeler.gates import CHECKS, GateDef, GateEffect, GateResult
from di.services.modeler.pack import Pack

TITLE_GATE = "G-VEH-TITLE"
BRAND_GATE = "G-VEH-BRAND"
TITLE_STATUS = "title_status"
LIEN_RELEASE = "lien_release"
TITLE_BRAND = "title_brand"
TRADE_IN = "trade_in"
REASON_CLEAR = "Clear title, no open finance"
REASON_PAYOFF = "Payoff of the customer's loan not confirmed"
REASON_MISSING = "Title and lien search not on file"
FALLBACK_ROUTES = ("retail", "auction", "dealer_trade", "salvage")
ODO_GATE = "G-VEH-ODO"
RECALL_GATE = "G-VEH-RECALL"
ODOMETER_STATEMENT = "odometer_statement"
RECALL_CHECK = "recall_check"
LEASE_END = "lease_end"
REASON_EXEMPT = "Odometer disclosure exempt"
REASON_NO_STATEMENT = "Odometer statement not on file"
NOT_ACTUAL = "Odometer reading is not the actual mileage"
REASON_STALE = "Recall check older than 30 days; re-run"
REASON_UNCHECKED = "Recall check not on file; run it"
REASON_NO_RETAIL = "Open recall: no retail until remedied"
NOW_KEY = "gateNow"  # the time `gate_hold` reads a case at (the value of valuers.fleet_evidence.NOW_KEY, not imported: a cycle)


def _routes(gate: GateDef, pack: Pack) -> tuple[str, ...]:
    """The routes the gate affects: the ref's `params.routes` that the pack has (the four channels by default)."""
    mine = {r.id for r in pack.routes}
    return tuple(r for r in gate.params.get("routes") or FALLBACK_ROUTES if r in mine)


def title_result(value: Mapping[str, Any] | None) -> tuple[bool, str, tuple[str, ...]]:
    """(passed, reason, evidence_missing) of a title search value: `title_status`, `lien_open`, `return_kind`,
    `payoff_confirmed`. None is no search on file."""
    if value is None or value.get("title_status") is None:
        return False, REASON_MISSING, (TITLE_STATUS,)
    if value.get("title_status") != "clear" or value.get("lien_open"):
        return False, REASON_CLEAR, (LIEN_RELEASE,)
    if value.get("return_kind") == TRADE_IN and not value.get("payoff_confirmed"):
        return False, REASON_PAYOFF, (LIEN_RELEASE,)
    return True, REASON_CLEAR, ()


def check_title_clear(case: Mapping[str, Any], pack: Pack, gate: GateDef) -> GateResult:
    """G-VEH-TITLE (module docstring)."""
    e = evidence_of(case, TITLE_STATUS)
    passed, reason, missing = title_result(dict(e.value) if e is not None else None)
    if passed:
        return GateResult(
            gate.id, True, GateEffect("block", (), gate.effect.hold_until_evidence, None), (), "Title clear, no open finance"
        )
    step = gate.effect.on_fail.step if gate.effect.on_fail else None
    return GateResult(
        gate.id, False, GateEffect("block", _routes(gate, pack), gate.effect.hold_until_evidence, step), missing, reason
    )


def check_title_brand(case: Mapping[str, Any], pack: Pack, gate: GateDef) -> GateResult:
    """G-VEH-BRAND (module docstring)."""
    e = evidence_of(case, TITLE_BRAND)
    brand = str(e.value.get("brand") or "") if e is not None else ""
    blocked = [str(b) for b in gate.params.get("retail_blocked_brands") or []]
    if not brand or brand not in [*(str(b) for b in gate.params.get("disclose_brands") or []), *blocked]:
        return GateResult(gate.id, True, GateEffect("disclose", (), False, None), (), "No title brand to disclose")
    text = f"Title brand: {brand}"
    if brand in blocked:
        routes = tuple(r.id for r in pack.routes if r.id == "retail")
        return GateResult(
            gate.id, False, GateEffect("block", routes, False, gate.effect.step), (),
            f"Title brand {brand}: retail blocked by pack", (text,),
        )  # fmt: skip
    return GateResult(gate.id, True, GateEffect("disclose", (), False, gate.effect.step), (), text, (text,))


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, int | float) and not isinstance(v, bool) else None


def _miles(v: float) -> str:
    return f"{v:,.0f}"


def _exempt(o: Mapping[str, Any], p: Mapping[str, Any], now: Any) -> bool:
    """The car needs no odometer disclosure: a model year before the pack's year, or as old as the pack's age."""
    year = _num(o.get("model_year"))
    if year is None:
        return False
    before, age = _num(p.get("exempt_model_year_before")), _num(p.get("exempt_age_years"))
    return (before is not None and year < before) or (age is not None and now is not None and now.year - year >= age)


def check_odometer(case: Mapping[str, Any], pack: Pack, gate: GateDef) -> GateResult:
    """G-VEH-ODO (module docstring)."""
    o = case.get("odometer") or {}
    p = gate.params
    quiet = GateEffect("block", (), False, None)
    if _exempt(o, p, parse_time(case.get(NOW_KEY))):
        return GateResult(gate.id, True, quiet, (), REASON_EXEMPT)
    shown = (NOT_ACTUAL,) if o.get("not_actual") else ()
    lease_return = o.get("return_kind") == LEASE_END
    missing = (
        (ODOMETER_STATEMENT,) if lease_return and not (o.get("statement_ref") or evidence_of(case, ODOMETER_STATEMENT)) else ()
    )
    photo, lease, tol = _num(o.get("photo_reading")), _num(o.get("lease_record")), _num(p.get("tolerance_miles")) or 0.0
    if photo is not None and lease is not None and abs(photo - lease) > tol:
        why = (
            f"Odometer photo reading {_miles(photo)} does not match the lease record {_miles(lease)} "
            f"(tolerance {_miles(tol)} miles)"
        )
        every = tuple(r.id for r in pack.routes)  # no route is valued, whatever its class: the car waits for a second inspection
        return GateResult(gate.id, False, GateEffect("block", every, True, None), missing, why, shown)
    if missing:
        step = GateEffect("require_step", (), False, gate.effect.step)
        return GateResult(gate.id, False, step, missing, REASON_NO_STATEMENT, shown)
    if shown:
        return GateResult(gate.id, True, GateEffect("disclose", (), False, None), (), NOT_ACTUAL, shown)
    return GateResult(gate.id, True, quiet, (), "Odometer verified")


def _only(ids: Any, pack: Pack) -> tuple[str, ...]:
    """The ids that are routes of the pack."""
    mine = {r.id for r in pack.routes}
    return tuple(r for r in ids or () if r in mine)


def check_open_recall(case: Mapping[str, Any], pack: Pack, gate: GateDef) -> GateResult:
    """G-VEH-RECALL (module docstring)."""
    r = case.get("recall") or {}
    p = gate.params
    now, checked = parse_time(case.get(NOW_KEY)), parse_time(r.get("checked_at"))
    ask = GateEffect("require_step", (), False, gate.effect.step)
    if checked is None:
        return GateResult(gate.id, False, ask, (RECALL_CHECK,), REASON_UNCHECKED)
    if now is not None and now - checked > timedelta(days=float(p.get("check_max_age_days") or 30)):
        return GateResult(gate.id, False, ask, (RECALL_CHECK,), REASON_STALE)
    if not r.get("open") or r.get("remedy_ref"):
        return GateResult(gate.id, True, GateEffect("block", (), False, None), (), "No open recall")
    ids = ", ".join(str(c["campaignId"]) for c in r.get("campaigns") or [] if isinstance(c, Mapping) and c.get("campaignId"))
    shown = (f"Open recall disclosed: {ids}" if ids else "Open recall disclosed",)
    fleet, minimum = _num(r.get("fleet_size")), _num(p.get("rental_fleet_min"))
    if fleet is not None and minimum is not None and fleet >= minimum:
        why = f"Open recall: a rental fleet of {minimum:.0f} or more may not sell until remedied"
        routes = _only(p.get("rental_fleet_block_routes"), pack)
        return GateResult(gate.id, False, GateEffect("block", routes, False, None), (), why, shown)
    routes = _only(p.get("block_routes") or ("retail",), pack)
    return GateResult(gate.id, False, GateEffect("block", routes, False, None), (), REASON_NO_RETAIL, shown)


CHECKS[TITLE_GATE] = check_title_clear
CHECKS[BRAND_GATE] = check_title_brand
CHECKS[ODO_GATE] = check_odometer
CHECKS[RECALL_GATE] = check_open_recall

"""The used-car title gates (plan 9, P9-9.8, stories UC-06 and UC-24). Pure. Implements the checks of registry entry I-2
for the catalogue gates `G-VEH-TITLE` and `G-VEH-BRAND` (Compliance, stage match); they run before any business rule (R20).

    check_title_clear(case, pack, gate) -> GateResult    G-VEH-TITLE: clear title, no open finance
    check_title_brand(case, pack, gate) -> GateResult    G-VEH-BRAND: a title brand is disclosed, some brands block retail

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

Never does: read the canonical store, the clock or a session, release a lien, or write a case. State title and brand law differ
and is unconfirmed per state; the pack's lists are data, and any wording built on them needs review by Kinective's Legal team
before it is relied on.
"""

from collections.abc import Mapping
from typing import Any

from di.services.modeler.evidence import evidence_of
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


CHECKS[TITLE_GATE] = check_title_clear
CHECKS[BRAND_GATE] = check_title_brand

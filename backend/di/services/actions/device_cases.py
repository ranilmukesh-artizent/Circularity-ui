"""Device case actions (plan 9, P9-6.8, story DV-05; registry entries I-15 and I-20).

    payout.decide   commit  {case_id, payout, reason}   decidePayouts: a person decides a payout that waits for Customer care

Only on a payout whose status is `waiting` (the pack's table gave a gap above GR-D11's limit, di.services.device.payout): the
amount stands as the payout (`decided`, with the person, the reason and the time), the `payout_gap` item closes, the journal
says who decided, and the `payout` instruction is sent. Refused: a payout above the quote (`validation_error`), a payout that
is not waiting (`conflict`, also a second decision), a payout the person prepared themselves (`conflict`, maker-checker), a
person without `decidePayouts` or of another tenant (the pipeline).
`payout.decide` is in `FORBIDDEN_ACTIONS` (di.services.agents.forbidden): no agent decides what a customer is paid, however the
call arrives (golden rule 10). Consumer-facing payout changes need Legal review per market before a customer relies on them.
"""

from typing import Any

from di.services.actions.pipeline import CallContext
from di.services.actions.registry import ACTIONS, ActionDef, ActionError, guard, implement
from di.services.cases import store
from di.services.device import payout

MAKER_CHECKER = "Maker-checker: you prepared this payout, so you cannot decide it."
_STR = {"req": True, "t": "string"}
ACTIONS.setdefault(
    "payout.decide",
    ActionDef(
        id="payout.decide", title="Decide a payout", verb="decide payouts",
        desc="Set the payout of a trade-in whose adjustment is above the automatic limit, with a reason that stays on record.",
        risk="commit", perm="decidePayouts", scope="case",
        input={
            "case_id": _STR, "payout": {"req": True, "t": "number"},
            "reason": {"req": True, "t": "string", "min": 10, "minText": "Add a reason of at least 10 characters."},
        },
    ),
)  # fmt: skip


@guard("payout.decide")
def decide_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    c = store.get(ctx.session, i["case_id"])
    if c is None:
        return "not_found", f"No live case {i['case_id']}."
    p = c.get("payout")
    if not isinstance(p, dict) or p.get("status") != "waiting":
        return "conflict", f"{i['case_id']} has no payout waiting for a decision."
    if not 0 <= float(i["payout"]) <= float(p["quote"]):
        return "validation_error", f"The payout is between $0 and the quote of ${p['quote']:g}."
    if p.get("prepared_by") == ctx.actor.id:
        return "conflict", MAKER_CHECKER
    return None


@implement("payout.decide")
def decide(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    c = store.get(ctx.session, i["case_id"], for_update=True)
    if c is None or not isinstance(c.get("payout"), dict) or c["payout"].get("status") != "waiting":
        raise ActionError("conflict", f"{i['case_id']} has no payout waiting for a decision.")  # decided in between
    payout.decided(ctx.session, c, float(i["payout"]), i["reason"].strip(), ctx.actor.id, ctx.now.isoformat())
    store.save(ctx.session, c)
    return {"case_id": c["id"], "payout": c["payout"]["adjusted"], "log": f"Payout decided: {payout.money(i['payout'])}"}

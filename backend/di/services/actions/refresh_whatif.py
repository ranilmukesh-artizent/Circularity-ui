"""Test the levers of a contract refresh proposal before publishing a new threshold (plan 9, P9-5.6, story CR-06).

    refresh.whatIf  read  {case_id, swap_threshold?: int 10-50, upgrades?: bool}
        -> {case_id, swap_threshold, upgrades, before, split, changed: [{serial, from, to}], fee_delta, renewal_delta,
            credit_total, flips_route, best_before, best_after, currency, note, log}

The case is priced again on a copy of its market's `refresh_tool_action` table with the swap threshold (percent of life left
under which a tool is swapped) and the upgrade rule moved (`contract_refresh.with_levers`), then matched and priced by the same
code the decision is made of: `tool_queue.refresh_actions` and `refresh_match` (the org's open refresh cases together, this one
on the copy), then `refresh_decision.quote`. It is never a second decider (R19). `before` and `split` are the tools kept,
swapped and upgraded as the table stands and with the levers; `fee_delta` is the proposed fee a month with the levers less
without, `renewal_delta` the change in renewal likelihood, `credit_total` the credits with the levers and `flips_route` whether
another route ranks first. Every figure is computed and `note` is a template over them (R16: no model writes a number; R8: it
says what it was before and what it would be).

A read: no case save, no journal row, no instruction, no unit held and no call to a source. A person or an agent may run it
(it approves, sends and publishes nothing, so it is not in FORBIDDEN_ACTIONS); the pipeline keeps the tenant boundary of the
case. Publishing a new threshold stays the table's maker-checker (`marketTable.*`, P9-4.2).
"""

from typing import Any

from di.services import refresh_decision
from di.services.actions.pipeline import CallContext
from di.services.actions.registry import ACTIONS, ActionDef, ActionError, guard, implement
from di.services.cases import intake, store, tool_queue
from di.services.modeler.valuers import contract_refresh

LOW, HIGH = 10, 50  # the swap threshold's range, percent of life left

ACTIONS.setdefault(
    "refresh.whatIf",
    ActionDef(
        id="refresh.whatIf", title="Test the proposal levers", verb="test the proposal levers",
        desc="Run a contract refresh again with another swap threshold (10 to 50% of life left) or the upgrade rule off, and see "
        "which tools change action and what it does to the fee, the credits and the renewal likelihood. Changes nothing and "
        "sends nothing.",
        risk="read", perm=None, scope="case",
        input={"case_id": {"req": True, "t": "string"}, "swap_threshold": {"t": "number"}, "upgrades": {"t": "boolean"}},
    ),
)  # fmt: skip


@guard("refresh.whatIf")
def what_if_guard(i: dict[str, Any], ctx: CallContext) -> tuple[str, str] | None:
    t, u = i.get("swap_threshold"), i.get("upgrades")
    if t is not None and (isinstance(t, bool) or not isinstance(t, int) or not LOW <= t <= HIGH):
        return "validation_error", f"The swap threshold is a whole number from {LOW} to {HIGH} (percent of life left)."
    if u is not None and not isinstance(u, bool):
        return "validation_error", "Upgrades is on or off."
    c = store.get(ctx.session, i["case_id"])
    if c is None or not intake.is_refresh(c):
        return "not_found", f"{i['case_id']} is not a contract refresh case."
    return None


def _split(acts: list[contract_refresh.ToolAction]) -> dict[str, int]:
    return contract_refresh.totals(acts)


def _note(before: dict[str, int], after: dict[str, int], n: int, fee: float, cur: str, t: int | None, up: bool | None) -> str:
    """R8: what it was and what it would be, as a template over computed numbers."""
    lever = ([f"swap below {t}% of life"] if t is not None else []) + (["upgrades off"] if up is False else [])
    show = lambda x: f"{x['keep']} keep, {x['swap']} swap, {x['upgrade']} upgrade"  # noqa: E731
    return (
        f"Before: {show(before)}. With {' and '.join(lever) or 'the table as it stands'}: {show(after)}; "
        f"{n} tool{'' if n == 1 else 's'} change action; the fee a month moves by {cur} {fee:+,.2f}. Nothing was changed or sent."
    )


@implement("refresh.whatIf")
def what_if(i: dict[str, Any], ctx: CallContext) -> dict[str, Any]:
    """A read (module docstring): the proposal priced on a copy of the table with the levers moved."""
    s = ctx.session
    c = store.get(s, i["case_id"])
    if c is None or not intake.is_refresh(c):
        raise ActionError("not_found", f"No contract refresh case {i['case_id']}.")
    t, up = i.get("swap_threshold"), i.get("upgrades")
    table = tool_queue.refresh_table(s, c)
    base = tool_queue.refresh_actions(s, c, table)
    if table is None or not base:
        raise ActionError("not_found", f"{c['id']} has no tools or no refresh table in force to test.")
    org, cid = str(c["owner"]), str(c["id"])
    moved = contract_refresh.with_levers(table, t, up)
    acts = tool_queue.refresh_actions(s, c, moved)
    q0 = refresh_decision.quote(s, c, base, tool_queue.refresh_match(s, org).get(cid, []))
    q1 = refresh_decision.quote(s, c, acts, tool_queue.refresh_match(s, org, {cid: moved}).get(cid, []))
    if q0 is None or q1 is None:
        raise ActionError("not_found", f"No approved tables to price {cid} with.")
    was = {a.serial: a.action for a in base}
    changed = [{"serial": a.serial, "from": was[a.serial], "to": a.action} for a in acts if was.get(a.serial) != a.action]
    p0, p1 = q0.pricing, q1.pricing
    fee = float(p1.proposed_fee_month - p0.proposed_fee_month)
    before, after = _split(base), _split(acts)
    return {
        "case_id": cid, "swap_threshold": t, "upgrades": up, "before": before, "split": after, "changed": changed,
        "fee_delta": round(fee, 2), "renewal_delta": round(p1.renewal_likelihood - p0.renewal_likelihood, 4),
        "credit_total": float(p1.credit_total), "flips_route": p1.best != p0.best, "best_before": p0.best,
        "best_after": p1.best, "currency": p1.currency, "note": _note(before, after, len(changed), fee, p1.currency, t, up),
        "log": "Levers tested: nothing was changed or sent",
    }  # fmt: skip

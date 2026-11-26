"""The contract refresh case panel's read (plan 9, P9-5.1, stories CR-01 and CR-08; later tasks fill tools, match, pricing,
approval, execution and outcome).

GET /api/screens/refresh/{case_id}
    {case_id, contract, window, lines, tools, match, pricing, approval, execution, outcome}
    `contract` is `{id, customer, market, start, end, notice, term_months, status}` as the case opened with it; `window` is
    `{opens, basis}`, `basis` "end" (the window counts back from the contract's end date) or "notice" (from its notice
    date); `lines` are `{serial, cls, model, fee, months}` from the contract's lines.
    `outcome` is null until the task that fills it.

    `execution` (P9-5.5, CR-05) is null until a person approves, then `{approval, route, approver, valid_until, steps: [{kind,
    system, state, ref, text}], done, back}`: the three steps of the approved plan (propsend, propdraft, propreserve; a route
    without units skips none, the reserve step is then acknowledged as simulated) with the reference each system returned
    ("Proposal sent PR-40201", "Contract lines drafted DL-40214", "Units reserved RU-40227"); `back` is `{to, reason}` when a unit
    was taken meanwhile and the decision went back to the Fleet desk.

    `match` (P9-5.3, CR-03) is one `{serial, need_id, cls, target, unit_id, rul, distance, source, why}` per swapped tool: the
    unit closest to the median life of the tools kept (`target`), from refurbished stock or a return planned to refurbish for
    it, each unit promised once across the org's open refresh cases (di.services.cases.tool_queue.refresh_match);
    `unit_id` is null and `why` says why when none fits. It proposes; a unit is reserved when a person approves.

    `tools` (P9-5.2, CR-02) is one `{serial, cls, action, reason, rul_pct, confidence, flag, end_of_parts, successor}` per line:
    keep, swap or upgrade from the market's `refresh_tool_action` table (di.services.modeler.valuers.contract_refresh);
    `tools_totals` is `{keep, swap, upgrade}` and `tools_hold` is "confidence" when a life estimate is Low confidence (the
    decision then waits for a person). `tools` is [] when the market has no table or the case has no market.

    `pricing` (P9-5.4, CR-04) is `{currency, rate_card_version, fees_version, credit_rules_version, term_months,
    current_fee_month,
    proposed_fee_month, saving_vs_new, renewal_likelihood, renewal_without, renewal_basis, credits: [{serial, amount,
    rule_version}], credit_total, credit_total_usd, lines: [{label, amount, cite}], routes: [{id, name, net, standard}], best,
    uplift}`: the money of the proposal, computed by di.services.modeler.valuers.contract_refresh from the market's `terms` rate
    card and `credit_rules` table in force today and the fleet's contract history (never by a model). `approval` is `{kind:
    "person", role, text, holds: [{id, reason, owner}]}`: GR-C1 sends credits over the pack's limit (USD, per proposal) to Sales,
    GR-C2 keeps every other proposal with the Fleet desk; never policy. Both are null without tools or the market's tables.

Refuses as `screens.case.case_page` does: 403 out_of_scope without the case pages, 404 not_found for an unknown case or one
that is not a contract refresh, 403 tenant_boundary outside the account's tenants or warehouse.

Facade (frontend/src/api/refresh.ts) -> this API
| export | served by |
|---|---|
| refreshView | GET /{case_id} |

Never writes. Every write goes through the action pipeline.
"""

from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from di.core.auth import Principal
from di.repositories.context import load_case
from di.services import refresh_decision
from di.services.cases import intake, tool_queue
from di.services.modeler.valuers import contract_refresh, tool_approval


def _tools(s: Session, c: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, int], str | None]:
    """The action of each tool (tool_queue.refresh_actions); ([], zeros, None) without a market, a term end or the market's
    table."""
    acts = tool_queue.refresh_actions(s, c)
    if not acts:
        return [], {a: 0 for a in contract_refresh.ACTIONS}, None
    out = [
        {
            "serial": a.serial, "cls": a.cls, "action": a.action, "reason": a.reason, "rul_pct": a.rul_pct,
            "confidence": a.confidence, "flag": contract_refresh.flag(a),
            "end_of_parts": a.end_of_parts.isoformat() if a.end_of_parts else None, "successor": a.successor,
        }
        for a in acts
    ]  # fmt: skip
    return out, contract_refresh.totals(acts), contract_refresh.hold_reason(acts)


def _match(s: Session, c: dict[str, Any]) -> list[dict[str, Any]]:
    """The like-life unit of each swap of this case (tool_queue.refresh_match, over the org's open refresh cases together)."""
    return tool_queue.refresh_match(s, str(c["owner"])).get(str(c["id"]), [])


def _pricing(
    s: Session, c: dict[str, Any], acts: list[contract_refresh.ToolAction], match: list[dict[str, Any]]
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """The proposal's pricing and who approves it; (None, None) without tools, a market or the market's tables in force."""
    q = refresh_decision.quote(s, c, acts, match)  # the same pricing the decision is made of (P9-5.5)
    if q is None:
        return None, None
    p, route = q.pricing, q.route
    pricing = {
        "currency": p.currency, "rate_card_version": p.rate_card_version, "fees_version": q.fees_version,
        "credit_rules_version": q.credit_version,
        "term_months": p.term_months, "current_fee_month": float(p.current_fee_month),
        "proposed_fee_month": float(p.proposed_fee_month), "saving_vs_new": float(p.saving_vs_new),
        "renewal_likelihood": p.renewal_likelihood, "renewal_without": p.renewal_without, "renewal_basis": p.renewal_basis,
        "credits": [{"serial": x.serial, "amount": float(x.amount), "rule_version": x.rule_version} for x in p.credits],
        "credit_total": float(p.credit_total), "credit_total_usd": round(q.credit_usd, 2),
        "lines": [{"label": x.label, "amount": float(x.amount), "cite": x.cite} for x in p.lines],
        "routes": [{"id": x.id, "name": x.name, "net": float(x.net), "standard": x.standard} for x in p.routes],
        "best": p.best, "uplift": float(p.uplift),
    }  # fmt: skip
    text = (
        f"Waits for {route.role}: {route.reasons[0]}"
        if route.role == tool_approval.CREDIT_ROLE
        else f"Waits for the {route.role}"
    )
    approval = {"kind": route.kind, "role": route.role, "text": text, "holds": [dict(h) for h in route.holds]}
    return pricing, approval


EXECUTION_TEXT = {  # step kind -> (before, after the system acknowledged it)
    "propsend": ("Send the proposal", "Proposal sent"),
    "propdraft": ("Draft the contract lines", "Contract lines drafted"),
    "propreserve": ("Reserve the units", "Units reserved"),
}


def _execution(c: dict[str, Any]) -> dict[str, Any] | None:
    """What the approval carried out: the three steps with the reference each system returned; None before an approval."""
    x = c.get("exec")
    if not x or "proposal" not in x:
        return None
    steps = []
    for st in x["steps"]:
        before, after = EXECUTION_TEXT.get(st["k"], (st["label"], st["label"]))
        ack = st.get("ack")
        steps.append(
            {"kind": st["k"], "system": st["sys"], "state": st["state"], "ref": ack["ref"] if ack else None,
             "text": f"{after} {ack['ref']}" if ack else before}
        )  # fmt: skip
    p = x["proposal"]
    return {
        "approval": x["ref"], "route": p["route"], "approver": p.get("approver"), "valid_until": p["valid_until"],
        "steps": steps, "done": all(st["state"] == "done" for st in steps), "back": c.get("refreshBack"),
    }  # fmt: skip


def view(s: Session, principal: Principal, case_id: str) -> dict[str, Any]:
    """The panel's read for one contract refresh case (module docstring)."""
    c = load_case(principal, s, case_id, "product", "case")
    if not intake.is_refresh(c):
        raise HTTPException(404, {"code": "not_found", "message": f"{case_id} is not a contract refresh case."})
    r = c.get("refresh") or {}
    tools, totals, hold = _tools(s, c)
    match = _match(s, c)
    pricing, approval = _pricing(s, c, tool_queue.refresh_actions(s, c), match)
    return {
        "case_id": case_id,
        "contract": {
            "id": r.get("contract_id") or c.get("contract_id"), "customer": r.get("customer"), "market": r.get("market"),
            "start": r.get("start_date"), "end": r.get("term_end"), "notice": r.get("notice_date"),
            "term_months": r.get("term_months"), "status": r.get("status"),
        },
        "window": {"opens": r.get("window_opens"), "basis": r.get("window_basis") or "end"},
        "lines": list(r.get("lines") or []),
        "tools": tools, "tools_totals": totals, "tools_hold": hold,
        "match": match,
        "pricing": pricing,
        "approval": approval,
        "execution": _execution(c),
        "outcome": None,
    }  # fmt: skip

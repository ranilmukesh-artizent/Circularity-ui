"""The contract refresh case panel's read (plan 9, P9-5.1, stories CR-01 and CR-08; later tasks fill tools, match, pricing,
approval, execution and outcome).

GET /api/screens/refresh/{case_id}
    {case_id, contract, window, lines, tools, match, pricing, approval, execution, outcome}
    `contract` is `{id, customer, market, start, end, notice, term_months, status}` as the case opened with it; `window` is
    `{opens, basis}`, `basis` "end" (the window counts back from the contract's end date) or "notice" (from its notice
    date); `lines` are `{serial, cls, model, fee, months}` from the contract's lines.
    `pricing`, `approval`, `execution` and `outcome` are null until the tasks that fill them.

    `match` (P9-5.3, CR-03) is one `{serial, need_id, cls, target, unit_id, rul, distance, source, why}` per swapped tool: the
    unit closest to the median life of the tools kept (`target`), from refurbished stock or a return planned to refurbish for
    it, each unit promised once across the org's open refresh cases (di.services.cases.tool_queue.refresh_match);
    `unit_id` is null and `why` says why when none fits. It proposes; a unit is reserved when a person approves.

    `tools` (P9-5.2, CR-02) is one `{serial, cls, action, reason, rul_pct, confidence, flag, end_of_parts, successor}` per line:
    keep, swap or upgrade from the market's `refresh_tool_action` table (di.services.modeler.valuers.contract_refresh);
    `tools_totals` is `{keep, swap, upgrade}` and `tools_hold` is "confidence" when a life estimate is Low confidence (the
    decision then waits for a person). `tools` is [] when the market has no table or the case has no market.

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
from di.services.cases import intake, tool_queue
from di.services.modeler.valuers import contract_refresh


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


def view(s: Session, principal: Principal, case_id: str) -> dict[str, Any]:
    """The panel's read for one contract refresh case (module docstring)."""
    c = load_case(principal, s, case_id, "product", "case")
    if not intake.is_refresh(c):
        raise HTTPException(404, {"code": "not_found", "message": f"{case_id} is not a contract refresh case."})
    r = c.get("refresh") or {}
    tools, totals, hold = _tools(s, c)
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
        "match": _match(s, c),
        "pricing": None,
        "approval": None,
        "execution": None,
        "outcome": None,
    }  # fmt: skip

"""The contract refresh case panel's read (plan 9, P9-5.1, stories CR-01 and CR-08; later tasks fill tools, match, pricing,
approval, execution and outcome).

GET /api/screens/refresh/{case_id}
    {case_id, contract, window, lines, tools, match, pricing, approval, execution, outcome}
    `contract` is `{id, customer, market, start, end, notice, term_months, status}` as the case opened with it; `window` is
    `{opens, basis}`, `basis` "end" (the window counts back from the contract's end date) or "notice" (from its notice
    date); `lines` are `{serial, cls, model, fee, months}` from the contract's lines. `match` is [] and
    `pricing`, `approval`, `execution` and `outcome` null until the tasks that fill them.

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

import calendar
from datetime import date
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from di.core import clock
from di.core.auth import Principal
from di.repositories import market_tables as tables_repo
from di.repositories import plm
from di.repositories.context import load_case
from di.services.cases import intake, life_evidence, refresh_window
from di.services.modeler.tables import JdmTable, ZenEvaluator
from di.services.modeler.valuers import contract_refresh, tool_inputs
from di.services.models.cost import FLOW, PACK


def _add_months(d: date, n: int) -> date:
    y, m = divmod(d.year * 12 + d.month - 1 + n, 12)
    return date(y, m + 1, min(d.day, calendar.monthrange(y, m + 1)[1]))


def _tools(s: Session, c: dict[str, Any], r: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, int], str | None]:
    """The action of each tool (contract_refresh.tool_actions) with the life of its serial, PLM's end of parts and the table in
    force today; ([], zeros, None) without a market, a term end or the market's table."""
    zero: dict[str, int] = {a: 0 for a in contract_refresh.ACTIONS}
    market, end, lines = r.get("market"), refresh_window.as_date(r.get("term_end")), list(r.get("lines") or [])
    if not market or end is None or not lines:
        return [], zero, None
    today, org = clock.now().date(), c.get("owner")
    tables_repo.ensure_seeded(s, PACK)
    row = tables_repo.effective(s, org, PACK, FLOW, str(market), "refresh_tool_action", today)
    if row is None:
        return [], zero, None
    life = {}
    for ln in lines:
        case = {"serial": ln["serial"], "owner": org, "cls": ln.get("cls")}
        res = tool_inputs.life_of(life_evidence.evidence(s, case), str(ln.get("cls") or ""), clock.now())
        if res is not None:
            life[str(ln["serial"])] = res
    eop = {k: plm.end_of_parts(s, org, k) for k in sorted({str(ln.get("cls")) for ln in lines if ln.get("cls")})}
    acts = contract_refresh.tool_actions(
        lines, life, eop, _add_months(end, int(r.get("term_months") or 0)), ZenEvaluator(), str(market),
        JdmTable.model_validate(row.body),
    )  # fmt: skip
    out = [
        {
            "serial": a.serial, "cls": a.cls, "action": a.action, "reason": a.reason, "rul_pct": a.rul_pct,
            "confidence": a.confidence, "flag": contract_refresh.flag(a),
            "end_of_parts": a.end_of_parts.isoformat() if a.end_of_parts else None, "successor": a.successor,
        }
        for a in acts
    ]  # fmt: skip
    return out, contract_refresh.totals(acts), contract_refresh.hold_reason(acts)


def view(s: Session, principal: Principal, case_id: str) -> dict[str, Any]:
    """The panel's read for one contract refresh case (module docstring)."""
    c = load_case(principal, s, case_id, "product", "case")
    if not intake.is_refresh(c):
        raise HTTPException(404, {"code": "not_found", "message": f"{case_id} is not a contract refresh case."})
    r = c.get("refresh") or {}
    tools, totals, hold = _tools(s, c, r)
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
        "match": [],
        "pricing": None,
        "approval": None,
        "execution": None,
        "outcome": None,
    }  # fmt: skip

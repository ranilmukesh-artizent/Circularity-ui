"""The contract refresh case panel's read (plan 9, P9-5.1, stories CR-01 and CR-08; later tasks fill tools, match, pricing,
approval, execution and outcome).

GET /api/screens/refresh/{case_id}
    {case_id, contract, window, lines, tools, match, pricing, approval, execution, outcome}
    `contract` is `{id, customer, market, start, end, notice, term_months, status}` as the case opened with it; `window` is
    `{opens, basis}`, `basis` "end" (the window counts back from the contract's end date) or "notice" (from its notice
    date); `lines` are `{serial, cls, model, fee, months}` from the contract's lines. `tools` and `match` are [] and
    `pricing`, `approval`, `execution` and `outcome` null until the tasks that fill them.

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
from di.services.cases import intake


def view(s: Session, principal: Principal, case_id: str) -> dict[str, Any]:
    """The panel's read for one contract refresh case (module docstring)."""
    c = load_case(principal, s, case_id, "product", "case")
    if not intake.is_refresh(c):
        raise HTTPException(404, {"code": "not_found", "message": f"{case_id} is not a contract refresh case."})
    r = c.get("refresh") or {}
    return {
        "case_id": case_id,
        "contract": {
            "id": r.get("contract_id") or c.get("contract_id"), "customer": r.get("customer"), "market": r.get("market"),
            "start": r.get("start_date"), "end": r.get("term_end"), "notice": r.get("notice_date"),
            "term_months": r.get("term_months"), "status": r.get("status"),
        },
        "window": {"opens": r.get("window_opens"), "basis": r.get("window_basis") or "end"},
        "lines": list(r.get("lines") or []),
        "tools": [],
        "match": [],
        "pricing": None,
        "approval": None,
        "execution": None,
        "outcome": None,
    }  # fmt: skip

"""The signed-in account's read context and what it may see: one definition of the demo's tenant boundary and
warehouse lock for reads (visCases, visRows, myCases, canRoute), shared by the screens, the live stream and Ask.

- `call_ctx(p, session)`: the action pipeline's context for a signed-in account (what the reads in di.reads take).
- `case_refusal` / `can_see_case`: whether an account may see one case (its owner tenant and its location).
- `visible_cases(ctx, tenant_filter)`: the demo's visCases (myCases with the top bar's tenant filter, S.tenant).
- `visible_rows(ctx, tenant_filter)`: the demo's visRows (the closed decisions in the account's tenants).
- `load_case(p, session, id, page, section)`: one live case for a page, with the case actions' refusals.
- `case_openable(s, p, ids)`: the demo's canRoute to a case page, for many ids.
"""

from collections.abc import Mapping
from typing import Literal

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from di import policy
from di.actions.pipeline import Actor, CallContext
from di.auth import Principal
from di.cases import store
from di.reads.common import Case, account
from di.reads.decisions import all_rows


def call_ctx(p: Principal, session: Session) -> CallContext:
    """The read helpers (di.reads) take the action pipeline's context: the signed-in account and the session."""
    return CallContext(actor=Actor(account=p.account, ctx=p.ctx), session=session)


def case_refusal(a: policy.Account, pctx: policy.Context | None, case: Mapping) -> Literal["tenant", "warehouse"] | None:
    """Why an account may not see a case (or any record with an owner tenant and a location): "tenant" outside its
    tenants, "warehouse" outside a Warehouse Manager's warehouse; None when it may."""
    if not policy.tenant_ok(a, case["owner"], pctx):
        return "tenant"
    if not policy.location_ok(a, case["location"]):
        return "warehouse"
    return None


def can_see_case(a: policy.Account, pctx: policy.Context | None, case: Mapping) -> bool:
    """The demo's tenant boundary and warehouse lock for one case: inside the account's tenants and its warehouse."""
    return case_refusal(a, pctx, case) is None


def visible_cases(ctx: CallContext, tenant_filter: str = "All", cases: list[Case] | None = None) -> list[Case]:
    """The demo's visCases: the cases (default: every live case) in the signed-in account's tenants and, for a
    Warehouse Manager, its warehouse, narrowed by the top bar's tenant filter (S.tenant; "All" narrows nothing).
    The system actor (no account) sees every case."""
    a = account(ctx)
    cs = store.all_cases(ctx.session) if cases is None else cases
    return [
        c
        for c in cs
        if (a is None or can_see_case(a, ctx.actor.ctx, c)) and (tenant_filter == "All" or c["owner"] == tenant_filter)
    ]


def visible_rows(ctx: CallContext, tenant_filter: str = "All") -> list[dict]:
    """The demo's visRows: the closed decisions in the account's tenants (no warehouse lock: they are not at a
    location), narrowed by the top bar's tenant filter."""
    a, pctx = account(ctx), ctx.actor.ctx
    return [
        r
        for r in all_rows()
        if (a is None or policy.tenant_ok(a, r["tenant"], pctx)) and (tenant_filter == "All" or r["tenant"] == tenant_filter)
    ]


def load_case(p: Principal, session: Session, case_id: str, page: str, section: str) -> Case:
    """One live case for a page: the page must be open to the account, the case must exist and be inside the account's
    tenants and warehouse (the refusals and messages of the case actions, di.actions.pipeline)."""
    p.require_page(page, section)
    c = store.get(session, case_id)
    if c is None:
        raise HTTPException(404, {"code": "not_found", "message": f"No live case {case_id}."})
    a = p.account
    if not can_see_case(a, p.ctx, c):
        msg = (
            f"{case_id} is at {c['location']}, outside your warehouse."
            if policy.policy(a).get("warehouseScoped")
            else f"{case_id} belongs to {c['owner']}, a tenant you cannot see. Request tenant access first."
        )
        raise HTTPException(403, {"code": "tenant_boundary", "message": msg})
    return c


def case_openable(s: Session, p: Principal, case_ids: set[str]) -> dict[str, bool]:
    """The demo's canRoute to a case page: the case exists, the account has the case page, and the case is in its
    tenants (and its warehouse, for a Warehouse Manager)."""
    ids = sorted(i for i in case_ids if i)
    if not ids or not policy.can_page(p.account, "product", "case"):
        return dict.fromkeys(ids, False)
    store.ensure(s)
    found = {
        r.id: {"owner": r.owner, "location": r.location}
        for r in s.execute(text("SELECT id, owner, location FROM case_record WHERE id = ANY(:i)"), {"i": ids})
    }
    return {i: i in found and can_see_case(p.account, p.ctx, found[i]) for i in ids}


def can_page(ctx: CallContext, page: str, section: str | None = None) -> bool:
    return policy.can_page(ctx.actor.account, page, section)

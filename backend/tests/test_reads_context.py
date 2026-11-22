"""What an account may see (di.repositories.context): one rule for the tenant boundary and the warehouse lock, used by the
screens, the live stream (di.services.stream.visible) and Ask's suggested next steps (di.services.ask.service.suggestions).

RT-1048 is Customer A's case at Warehouse 1: wm-1 (Warehouse 1) may see it, wm-2 (Warehouse 2) may not, planner-b
(Customer B) may not.
"""

from di.core import policy
from di.core.auth import Principal, load_context
from di.core.db import SessionLocal
from di.repositories.context import can_see_case, case_refusal, visible_cases, visible_rows
from di.services.actions.pipeline import Actor, CallContext
from di.services.ask import service
from di.services.cases import store
from di.services.stream import visible
from tests import starting


def setup_module():
    starting.reset()


def _ctx(s, account_id: str) -> CallContext:
    pctx = load_context(s)
    return CallContext(actor=Actor(account=policy.account(account_id, pctx), ctx=pctx), session=s)


def test_case_refusal_names_the_boundary():
    with SessionLocal() as s:
        c = store.get(s, "RT-1048")
        assert (c["owner"], c["location"]) == ("Customer A", "Warehouse 1")
        refusal = {}
        for a in ("wm-1", "wm-2", "planner-b", "admin"):
            ctx = _ctx(s, a)
            refusal[a] = case_refusal(ctx.actor.account, ctx.actor.ctx, c)
        assert refusal == {"wm-1": None, "wm-2": "warehouse", "planner-b": "tenant", "admin": None}
        ctx = _ctx(s, "wm-2")
        assert can_see_case(ctx.actor.account, ctx.actor.ctx, c) is False


def test_visible_cases_and_rows_follow_the_tenant_filter():
    with SessionLocal() as s:
        admin = _ctx(s, "admin")
        every = visible_cases(admin)
        assert len(every) == len(store.all_cases(s))
        a_only = visible_cases(admin, "Customer A")
        assert a_only and {c["owner"] for c in a_only} == {"Customer A"}
        wm2 = visible_cases(_ctx(s, "wm-2"))
        assert wm2 and {c["location"] for c in wm2} == {"Warehouse 2"}
        rows_b = visible_rows(_ctx(s, "planner-b"))
        assert rows_b and {r["tenant"] for r in rows_b} == {"Customer B"}
        assert visible_rows(admin, "Customer C") == [r for r in visible_rows(admin) if r["tenant"] == "Customer C"]


def test_ask_suggestions_keep_the_warehouse_lock(monkeypatch):
    """A Warehouse Manager of another warehouse gets no next step for a case outside its warehouse (the tenant check
    alone let one through). Every case is given a pressable next step, so only the scope decides."""

    def step(c, ctx):  # next_step's signature
        return {"kind": "act", "label": "Go", "action": "evidence.request", "input": {"case_id": c["id"]}}

    monkeypatch.setattr(service, "next_step", step)
    with SessionLocal() as s:
        assert [x["case_id"] for x in service.suggestions(_ctx(s, "wm-1"), ["RT-1048"])] == ["RT-1048"]
        assert service.suggestions(_ctx(s, "wm-2"), ["RT-1048"]) == []
        assert service.suggestions(_ctx(s, "planner-b"), ["RT-1048"]) == []


def test_stream_visibility_uses_the_same_rule():
    with SessionLocal() as s:
        pctx = load_context(s)

    def p(aid: str) -> Principal:
        return Principal(policy.account(aid, pctx), pctx)

    ev = {"tenant": "Customer A", "location": "Warehouse 1", "kind": "case", "payload": {}}
    assert [visible(p(a), ev) for a in ("wm-1", "wm-2", "planner-b", "admin")] == [True, False, False, True]
    # an event with no tenant (a workspace event) is not scoped to a case
    assert visible(p("wm-2"), {"tenant": None, "location": None, "kind": "case", "payload": {}}) is True

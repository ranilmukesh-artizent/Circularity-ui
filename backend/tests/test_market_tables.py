"""P9-4.2 (story SD-03; registry entry I-15; R21): per-market rate cards and decision tables with maker-checker.

A table is computed rules, not language: no step here reads or writes free text, so the model-first rule (R16) has nothing to
route. A table version is a new approvable object: the person who saved or submitted it never approves it, no agent approves
or rejects it, and a table of another customer's org unit is out of reach. A priced line cites the version in force on its
decision date (`effective`), so a later change never rewrites an earlier price.
"""

from datetime import date
from decimal import Decimal

import pytest

from di.core import policy
from di.core.auth import load_context
from di.core.db import SessionLocal
from di.repositories import market_tables
from di.services.actions.pipeline import Actor, CallContext, invoke
from di.services.agents.forbidden import FORBIDDEN_ACTIONS, forbidden
from di.services.modeler import tables
from tests import starting
from tests.helpers import call

PACK, FLOW = "tool_fleet", "service_desk"
MAKER_CHECKER = "Maker-checker: you changed this table, so you cannot approve it."
FUNCTION_NODE = "Function nodes run code and are not allowed in a decision table."


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    with SessionLocal() as s:
        market_tables.ensure_seeded(s, PACK)
        s.commit()
    yield
    starting.reset()


# ---------------------------------------------------------------- helpers
def ok(r: dict) -> dict:
    assert r.get("ok"), r
    return r["output"]


def eff(market: str, name: str, as_of: date, org: str | None = None) -> market_tables.TableRow | None:
    with SessionLocal() as s:
        return market_tables.effective(s, org, PACK, FLOW, market, name, as_of)


def labour(value: int, valid_from: str = "2026-11-01", **extra) -> dict:
    return {
        "pack": PACK, "flow": FLOW, "market": "FR", "name": "labour", "kind": "rate_card", "valid_from": valid_from,
        "currency": "EUR", "body": {"values": {"per_hour": value}}, **extra,
    }  # fmt: skip


def submitted_labour_v2() -> str:
    out = ok(call("marketTable.save", labour(48), "finance"))
    assert out["version"] == 2 and out["status"] == "draft"
    ok(call("marketTable.submit", {"id": out["id"]}, "finance"))
    return out["id"]


def cover_terms(market: str = "US") -> tables.JdmTable:
    row = eff(market, "cover_terms", date(2026, 10, 7))
    assert row is not None
    return tables.JdmTable.model_validate(row.body)


# ---------------------------------------------------------------- SD-03: versions and dates
def test_sd_03_lines_cite_table_version():
    row = eff("DE", "labour", date(2026, 10, 7))
    assert row is not None and row.version == 1 and row.status == "approved"
    card = tables.rate_card(row)
    assert card.currency == "EUR" and tables.rate(card, "per_hour") == Decimal("42")
    ref = tables.TableRef(PACK, FLOW, "DE", "labour", row.version)
    assert str(ref) == "DE labour rates v1"
    assert row.approved_by == "pack tool_fleet v3.2.0"


def test_sd_03_rate_names_card_and_key():
    row = eff("UK", "labour", date(2026, 10, 7))
    assert row is not None
    with pytest.raises(KeyError, match="UK labour.*no_such"):
        tables.rate(tables.rate_card(row), "no_such")


def test_sd_03_seeding_runs_once():
    with SessionLocal() as s:
        market_tables.ensure_seeded(s, PACK)
        market_tables.ensure_seeded(s, PACK)
        s.commit()
        rows = market_tables.listed(s, PACK, FLOW, "DE", None)
    names = sorted({r.name for r in rows})
    assert names == ["cover_terms", "credit_rules", "labour", "parts", "terms"]
    assert [r.version for r in rows if r.name == "parts"] == [2, 1]  # newest first


def test_sd_03_change_needs_maker_checker():
    tid = submitted_labour_v2()
    r = call("marketTable.approve", {"id": tid}, "finance")  # Finance saved and submitted it, and has no approve.packs either
    assert r["ok"] is False and r["error"]["code"] == "out_of_scope"
    assert ok(call("marketTable.approve", {"id": tid}, "approver"))["status"] == "approved"
    new = eff("FR", "labour", date(2026, 11, 1))
    assert new is not None and new.version == 2 and tables.rate(tables.rate_card(new), "per_hour") == Decimal("48")
    old = eff("FR", "labour", date(2026, 10, 15))
    assert old is not None and old.version == 1 and tables.rate(tables.rate_card(old), "per_hour") == Decimal("46")
    assert old.valid_to == date(2026, 10, 31)  # the previous version ends the day before the new one starts


def test_sd_03_effective_on_decision_date():
    sept, octo = eff("DE", "parts", date(2026, 9, 30)), eff("DE", "parts", date(2026, 10, 1))
    assert sept is not None and octo is not None
    assert (sept.version, octo.version) == (1, 2)
    assert (sept.valid_from, sept.valid_to, octo.valid_from) == (date(2026, 9, 1), date(2026, 9, 30), date(2026, 10, 1))
    assert eff("DE", "parts", date(2026, 8, 31)) is None  # nothing was in force before September


def test_sd_03_own_org_table_wins_over_the_shared_one():
    body = labour(50) | {"org_unit_id": "Customer A", "market": "DE", "currency": "EUR"}
    out = ok(call("marketTable.save", body, "admin"))
    ok(call("marketTable.submit", {"id": out["id"]}, "admin"))
    ok(call("marketTable.approve", {"id": out["id"]}, "approver"))
    own = eff("DE", "labour", date(2026, 11, 2), "Customer A")
    shared = eff("DE", "labour", date(2026, 11, 2), "Customer B")
    assert own is not None and own.org_unit_id == "Customer A" and own.version == 1
    assert shared is not None and shared.org_unit_id is None


def test_sd_03_save_checks_the_pack():
    for patch, word in (
        ({"market": "JP"}, "market"),
        ({"name": "bonus"}, "table"),
        ({"currency": "USD"}, "EUR"),
        ({"body": {"values": {"per_hour": "x"}}}, "number"),
        ({"valid_from": "2026-13-01"}, "date"),
    ):
        r = call("marketTable.save", labour(48) | patch, "finance")
        assert r["ok"] is False and r["error"]["code"] == "validation_error" and word in r["error"]["message"], (patch, r)


def test_sd_03_reject_keeps_the_old_version_in_force():
    tid = submitted_labour_v2()
    r = call("marketTable.reject", {"id": tid, "reason": "no"}, "approver")
    assert r["ok"] is False and r["error"]["code"] == "validation_error"  # a reason of 15 characters
    assert ok(call("marketTable.reject", {"id": tid, "reason": "The agreed rate is 47."}, "approver"))["status"] == "rejected"
    row = eff("FR", "labour", date(2026, 12, 1))
    assert row is not None and row.version == 1
    rows = ok(call("marketTable.list", {"pack": PACK, "flow": FLOW, "market": "FR"}, "finance"))["tables"]
    mine = next(t for t in rows if t["id"] == tid)
    assert mine["status"] == "rejected" and mine["reason"] == "The agreed rate is 47." and mine["created_by"] == "finance"
    assert mine["label"] == "FR labour rates v2"


def test_sd_03_only_own_draft_is_edited():
    out = ok(call("marketTable.save", labour(48), "finance"))
    again = ok(call("marketTable.save", labour(49) | {"id": out["id"]}, "finance"))
    assert again["id"] == out["id"] and again["version"] == 2
    r = call("marketTable.save", labour(51) | {"id": out["id"]}, "admin")
    assert r["ok"] is False and r["error"]["code"] == "conflict"
    ok(call("marketTable.submit", {"id": out["id"]}, "finance"))
    r = call("marketTable.save", labour(52) | {"id": out["id"]}, "finance")  # submitted: no longer a draft
    assert r["ok"] is False and r["error"]["code"] == "conflict"


# ---------------------------------------------------------------- the evaluator
def test_cover_terms_cordless_swap():
    ev = tables.ZenEvaluator()
    base = {"market": "US", "family": "CRH", "cover_type": "fleet", "age_months": 18}
    out = ev.evaluate(cover_terms(), base)
    assert out.outputs["swap_allowed"] is True and out.outputs["repair_covered"] is True
    assert out.outputs["reason"] == "Fleet cover: swap allowed for cordless tools"
    assert len(out.matched) == 1 and out.trace
    other = ev.evaluate(cover_terms(), base | {"family": "CMH"})
    assert other.outputs["swap_allowed"] is False and other.outputs["reason"] == "Fleet cover: repair covered"
    warranty = ev.evaluate(cover_terms(), base | {"cover_type": "warranty", "family": "CMH", "age_months": 25})
    assert warranty.outputs["reason"] == "No cover" and warranty.outputs["repair_covered"] is False


def test_credit_rules_first_hit():
    ev = tables.ZenEvaluator()
    row = eff("UK", "credit_rules", date(2026, 10, 7))
    assert row is not None
    t = tables.JdmTable.model_validate(row.body)
    base = {"market": "UK", "family": "CMH", "age_months": 30}
    assert ev.evaluate(t, base | {"life_used_pct": 85}).outputs == {"credit_pct": 0.25, "credit_cap": 400}
    assert ev.evaluate(t, base | {"life_used_pct": 50}).outputs == {"credit_pct": 0.2, "credit_cap": 300}
    assert ev.evaluate(t, base | {"life_used_pct": 10}).outputs == {"credit_pct": 0.1, "credit_cap": 150}


def function_body() -> dict:
    body = cover_terms().model_dump(mode="json", exclude_none=True)
    code = "export const handler = async () => ({})"
    body["nodes"].append({"id": "fn1", "type": "functionNode", "name": "Run", "content": code})
    return body


def test_function_node_refused():
    assert FUNCTION_NODE in tables.validate_table(function_body())
    body = {**labour(48), "kind": "decision_table", "name": "cover_terms", "body": function_body()}
    r = call("marketTable.save", body, "finance")
    assert r["ok"] is False and r["error"]["code"] == "validation_error" and FUNCTION_NODE in r["error"]["message"]
    with pytest.raises(tables.TableError, match="Function nodes"):
        tables.ZenEvaluator().evaluate(tables.JdmTable.model_validate(function_body()), {})


def test_custom_node_and_shape_refused():
    body = cover_terms().model_dump(mode="json", exclude_none=True)
    body["nodes"].append({"id": "c1", "type": "customNode", "name": "X"})
    assert any("not allowed" in p for p in tables.validate_table(body))
    body = cover_terms().model_dump(mode="json", exclude_none=True)
    body["nodes"] = [n for n in body["nodes"] if n["type"] != "outputNode"]
    assert any("one output" in p for p in tables.validate_table(body))


def test_undeclared_input_refused():
    body = cover_terms().model_dump(mode="json", exclude_none=True)
    for n in body["nodes"]:
        if n["type"] == "decisionTableNode":
            n["content"]["inputs"][1]["field"] = "secret_margin"
    declared = tables.market_spec(PACK).table("cover_terms").inputs
    problems = tables.validate_table(body, declared=declared)
    assert any("secret_margin" in p and "not an input" in p for p in problems)
    assert tables.validate_table(cover_terms().model_dump(mode="json", exclude_none=True), declared=declared) == []


def test_market_table_test_action_never_writes():
    row = eff("US", "cover_terms", date(2026, 10, 7))
    assert row is not None
    inputs = {"market": "US", "family": "CRH", "cover_type": "fleet", "age_months": 18}
    out = ok(call("marketTable.test", {"id": row.id, "inputs": inputs}, "finance"))
    assert out["outputs"]["swap_allowed"] is True and out["matched"] and out["trace"]
    card = eff("US", "labour", date(2026, 10, 7))
    assert card is not None
    assert ok(call("marketTable.test", {"id": card.id, "inputs": {}}, "finance"))["outputs"] == {"per_hour": 58}
    with SessionLocal() as s:
        before = len(market_tables.listed(s, PACK, FLOW, "US", None))
    assert before == 6


# ---------------------------------------------------------------- R21: maker is never checker, no agent, tenants
def test_market_table_maker_cannot_approve():
    # Admin may draft and approve, so only maker-checker stops Admin approving the table Admin saved and submitted
    out = ok(call("marketTable.save", labour(47, "2026-12-01"), "admin"))
    ok(call("marketTable.submit", {"id": out["id"]}, "admin"))
    r = call("marketTable.approve", {"id": out["id"]}, "admin")
    assert (r["ok"], r["error"]["code"], r["error"]["message"]) == (False, "conflict", MAKER_CHECKER)
    # the one who only submitted it is a maker too: Finance drafts, Admin submits, neither approves
    out = ok(call("marketTable.save", labour(46, "2026-12-01"), "finance"))
    ok(call("marketTable.submit", {"id": out["id"]}, "admin"))
    r = call("marketTable.approve", {"id": out["id"]}, "admin")
    assert (r["ok"], r["error"]["code"], r["error"]["message"]) == (False, "conflict", MAKER_CHECKER)
    assert call("marketTable.approve", {"id": out["id"]}, "finance")["error"]["code"] == "out_of_scope"
    assert ok(call("marketTable.approve", {"id": out["id"]}, "approver"))["status"] == "approved"


def test_market_table_approve_needs_submitted_and_permission():
    out = ok(call("marketTable.save", labour(48), "finance"))
    r = call("marketTable.approve", {"id": out["id"]}, "approver")  # still a draft
    assert r["ok"] is False and r["error"]["code"] == "conflict"
    ok(call("marketTable.submit", {"id": out["id"]}, "finance"))
    r = call("marketTable.approve", {"id": out["id"]}, "engineer")
    assert r["ok"] is False and r["error"]["code"] == "out_of_scope"
    r = call("marketTable.save", labour(48), "approver")  # the checker role does not draft
    assert r["ok"] is False and r["error"]["code"] == "out_of_scope"


def test_market_table_agent_cannot_approve():
    tid = submitted_labour_v2()
    assert forbidden("marketTable.approve") and forbidden("marketTable.reject")
    assert "marketTable.approve" in FORBIDDEN_ACTIONS and "marketTable.reject" in FORBIDDEN_ACTIONS
    for action, body in (
        ("marketTable.approve", {"id": tid}),
        ("marketTable.reject", {"id": tid, "reason": "An agent may not reject it."}),
    ):
        for confirmed in (False, True):
            with SessionLocal() as s:
                pctx = load_context(s)
                ctx = CallContext(
                    actor=Actor(account=policy.account("approver", pctx), ctx=pctx),
                    session=s, preparer="coordinator", confirmed=confirmed,
                )  # fmt: skip
                r = invoke(action, body, ctx)
                s.commit()
            assert r["ok"] is False and r["error"]["code"] == "approval_required", (action, confirmed, r)
    # an agent's draft is held for a person, not saved
    with SessionLocal() as s:
        pctx = load_context(s)
        ctx = CallContext(actor=Actor(account=policy.account("finance", pctx), ctx=pctx), session=s, preparer="coordinator")
        r = invoke("marketTable.save", labour(49), ctx)
        s.commit()
    assert r["ok"] is True and "held" in r["output"]
    rows = ok(call("marketTable.list", {"pack": PACK, "flow": FLOW, "market": "FR", "name": "labour"}, "finance"))["tables"]
    assert [t["version"] for t in rows if t["status"] != "approved"] == [2]  # only the person's own v2


def test_market_table_tenant_boundary():
    own = ok(call("marketTable.save", labour(50) | {"org_unit_id": "Customer A", "market": "DE", "currency": "EUR"}, "admin"))
    ok(call("marketTable.submit", {"id": own["id"]}, "admin"))
    for action, body in (
        ("marketTable.list", {"pack": PACK, "org_unit_id": "Customer A"}),
        ("marketTable.test", {"id": own["id"], "inputs": {}}),
        ("marketTable.save", labour(50) | {"org_unit_id": "Customer A"}),
        ("marketTable.save", labour(51) | {"id": own["id"], "org_unit_id": "Customer A"}),
        ("marketTable.submit", {"id": own["id"]}),
    ):
        r = call(action, body, "planner.b")
        assert r["ok"] is False and r["error"]["code"] == "tenant_boundary", (action, r)
    r = call("marketTable.approve", {"id": own["id"]}, "planner.b")  # refused for the permission, and for the tenant
    assert r["ok"] is False and r["error"]["code"] in ("out_of_scope", "tenant_boundary")
    listed = ok(call("marketTable.list", {"pack": PACK, "flow": FLOW, "market": "DE"}, "planner.b"))["tables"]
    assert all(t["org_unit_id"] is None for t in listed)  # the shared tables only
    r = call("marketTable.save", labour(50), "planner.b")  # a shared table is not a tenant's to change
    assert r["ok"] is False and r["error"]["code"] == "tenant_boundary"


def test_sd_03_finance_sees_modeler_tables():
    pctx = load_context(SessionLocal())
    assert policy.can_page(policy.account("finance", pctx), "modeler")
    assert policy.can(policy.account("finance", pctx), "manageMarketTables", pctx)
    r = starting_screen("finance")
    assert r["can"]["edit"] is False  # flows are read only for Finance


def starting_screen(user: str) -> dict:
    from tests.helpers import client, h

    resp = client.get("/api/screens/modeler?template=tool_fleet", headers=h(user))
    assert resp.status_code == 200, resp.text
    return resp.json()

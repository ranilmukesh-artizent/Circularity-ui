"""B8: the action endpoint behaves like the demo's invoke() (docs/BACKEND_STEPS.md)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from di import golden, policy
from di.actions.registry import ACTIONS, ActionDef, ActionError
from di.db import engine
from di.main import app

client = TestClient(app)
_tokens: dict[str, dict] = {}


def h(user: str) -> dict:
    if user not in _tokens:
        r = client.post("/api/auth/login", json={"username": user, "password": "x"})
        _tokens[user] = {"Authorization": "Bearer " + r.json()["access_token"]}
    return _tokens[user]


def call(action: str, body: dict, user: str | None = "admin", **headers):
    return client.post(f"/api/actions/{action}", json=body, headers=(h(user) if user else {}) | headers)


def valid_input(a: ActionDef) -> dict:
    """A minimal input that passes validation: required fields with their example or a value of the right type."""
    out = {}
    for k, v in a.input.items():
        if not v.get("req"):
            continue
        t = v.get("t")
        x = v.get("ex")
        if x is None:
            x = {"string": "x" * max(1, v.get("min") or 1), "number": 1, "boolean": True, "array": [], "object": {}}.get(t, "x")
        if k == "case_id":
            x = "RT-1048"
        if isinstance(x, str) and v.get("min"):
            x = x.ljust(v["min"], ".")
        out[k] = x
    return out


ACCOUNTS = [a.id for a in policy.accounts()]


def lacking(perm: str) -> str | None:
    return next((acct for acct in ACCOUNTS if not policy.can(policy.account(acct), perm)), None)


def setup_module():
    with engine.begin() as conn:
        conn.execute(text("UPDATE delegation SET enabled = true"))
        conn.execute(text("DELETE FROM tenant_grant"))


# ---------------------------------------------------------------- every action
def test_catalog_has_the_demos_76_actions():
    assert len(ACTIONS) == 76
    cat = client.get("/api/actions", headers=h("planner.a")).json()
    by_id = {a["id"]: a for a in cat}
    assert by_id["decision.submit"]["allowed"] and not by_id["decision.approve"]["allowed"]
    assert not by_id["adapter.acknowledge"]["allowed"]  # system only


@pytest.mark.parametrize("action_id", sorted(a.id for a in ACTIONS.values() if any(v.get("req") for v in a.input.values())))
def test_missing_input_is_a_validation_error(action_id):
    a = ACTIONS[action_id]
    first = next(k for k, v in a.input.items() if v.get("req"))
    body = valid_input(a)
    body.pop(first)
    r = call(action_id, body)
    assert r.status_code == 400 and r.json() == {
        "ok": False,
        "error": {"code": "validation_error", "message": f'Missing "{first}".'},
    }


@pytest.mark.parametrize("action_id", sorted(a.id for a in ACTIONS.values() if a.permission and a.risk != "system"))
def test_wrong_role_is_out_of_scope(action_id):
    a = ACTIONS[action_id]
    who = lacking(a.permission)
    if who is None:
        pytest.skip("every account has this permission")
    r = call(action_id, valid_input(a), user=policy.sign_in_email(policy.account(who)))
    body = r.json()
    assert r.status_code == 403 and body["error"]["code"] == "out_of_scope", body
    assert body["error"]["message"] == f"The {policy.account(who).role} view cannot {a.verb or a.title.lower()}."


def test_system_actions_are_refused_over_http():
    r = call("adapter.acknowledge", {"case_id": "RT-1048"})
    assert r.status_code == 403 and r.json()["error"]["message"] == "Only an enterprise system acknowledges instructions."


def test_anonymous_callers():
    r = call("decision.submit", {"case_id": "RT-1048"}, user=None)
    assert r.status_code == 401 and r.json()["error"] == {"code": "out_of_scope", "message": "Sign in first."}
    assert call("decision.submit", {}, user=None).status_code == 400  # input is validated first, as in the demo


def test_unknown_action_and_bad_body():
    assert call("no.such.action", {}).status_code == 404
    r = client.post("/api/actions/decision.submit", json=[1, 2], headers=h("admin"))
    assert r.status_code == 400


# ---------------------------------------------------------------- parity with the demo's refusals (golden actions.json)
def golden_step(action: str, as_: str) -> dict:
    return next(s for s in golden.load("actions")["steps"] if s["action"] == action and s["as"] == as_ and not s["result"]["ok"])


def test_tenant_boundary_message_matches_the_demo():
    expected = golden_step("case.get", "planner-b")["result"]["error"]
    r = call("decision.submit", {"case_id": "RT-1048"}, user="planner.b")
    assert r.status_code == 403 and r.json()["error"] == expected


def test_warehouse_lock():
    r = call("evidence.request", {"case_id": "RT-1048"}, user="warehouse2")
    assert r.status_code == 403 and r.json()["error"] == {
        "code": "tenant_boundary",
        "message": "RT-1048 is at Warehouse 1, outside your warehouse.",
    }


def test_rationale_rule_matches_the_demo():
    expected = golden_step("decision.approve", "approver")["result"]["error"]
    r = call("decision.approve", {"case_id": "RT-1048", "rationale": "short", "reviewed": True}, user="approver")
    assert r.status_code == 400 and r.json()["error"] == expected


def test_unknown_case():
    r = call("decision.submit", {"case_id": "RT-9999"}, user="planner.a")
    assert r.status_code == 404 and r.json()["error"]["message"] == "No live case RT-9999."


def test_valid_call_without_a_handler_yet():
    r = call("analytics.query", {"metric": "recovery"}, user="executive")
    assert r.status_code == 501 and r.json()["error"]["code"] == "not_implemented"


# ---------------------------------------------------------------- the full path, with test handlers
@pytest.fixture
def test_actions():
    seen = []

    def act(i, ctx):
        if i.get("fail"):
            raise ActionError("conflict", "Not possible in the current state")
        seen.append(i)
        return {"ref": f"T-{len(seen)}", "case_id": i.get("case_id")}

    defs = {
        "test.act": ActionDef(
            "test.act",
            "Test act",
            "",
            "act",
            None,
            "case",
            {"case_id": {"t": "string", "req": True}},
            handler=act,
            idem=lambda i, ctx: i["case_id"] + ":" + str(i.get("n", 0)),
            dup_text="Already tested",
        ),
        "test.commit": ActionDef("test.commit", "Test commit", "", "commit", None, "none", {}, handler=act),
        "test.read": ActionDef("test.read", "Test read", "", "read", None, "none", {}, handler=lambda i, ctx: {"rows": [1, 2]}),
    }
    ACTIONS.update(defs)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM domain_event WHERE type LIKE 'action.test.%'"))
        conn.execute(text("DELETE FROM action_journal WHERE action LIKE 'test.%'"))
    yield seen
    for k in defs:
        ACTIONS.pop(k)


def journal(action):
    with engine.connect() as conn:
        return conn.execute(text("SELECT * FROM action_journal WHERE action = :a ORDER BY seq"), {"a": action}).mappings().all()


def test_state_change_is_journaled_once_with_an_event(test_actions):
    r = call("test.act", {"case_id": "RT-1048", "password": "hunter2"}, user="planner.a")
    body = r.json()
    assert (
        r.status_code == 200
        and body["ok"]
        and body["output"]["ref"] == "T-1"
        and body["seq"]
        and body["key"] == "test.act:RT-1048:0"
    )
    rows = journal("test.act")
    assert len(rows) == 1 and rows[0]["actor"] == "planner-a" and rows[0]["case_id"] == "RT-1048"
    assert "password" not in rows[0]["input"]  # secrets are never stored
    assert rows[0]["output_ref"] == {"ref": "T-1", "case_id": "RT-1048"}
    with engine.connect() as conn:
        ev = conn.execute(text("SELECT type FROM domain_event WHERE seq = :s"), {"s": body["seq"]}).scalars().all()
    assert ev == ["action.test.act"]

    again = call("test.act", {"case_id": "RT-1048"}, user="planner.a")
    assert again.status_code == 409 and again.json()["error"] == {
        "code": "duplicate",
        "message": "Already tested. Nothing was created twice.",
    }
    assert len(test_actions) == 1


def test_undo_frees_the_idempotency_key(test_actions):
    seq = call("test.act", {"case_id": "RT-1048", "n": 7}, user="planner.a").json()["seq"]
    assert client.post("/api/journal/undo", json={"seqs": [seq]}, headers=h("planner.b")).status_code == 403  # not theirs
    assert client.post("/api/journal/undo", json={"seqs": [seq]}, headers=h("planner.a")).json() == {"undone": [seq]}
    assert call("test.act", {"case_id": "RT-1048", "n": 7}, user="planner.a").status_code == 200


def test_client_idempotency_key(test_actions):
    assert call("test.commit", {}, **{"Idempotency-Key": "abc-1"}).status_code == 200
    assert call("test.commit", {}, **{"Idempotency-Key": "abc-1"}).status_code == 409
    assert call("test.commit", {}, **{"Idempotency-Key": "abc-2"}).status_code == 200


def test_reads_are_not_journaled(test_actions):
    r = call("test.read", {})
    assert r.json() == {"ok": True, "output": {"rows": [1, 2]}, "key": None, "action": "test.read"}
    assert journal("test.read") == []


def test_handler_refusal_rolls_back(test_actions):
    r = call("test.act", {"case_id": "RT-1048", "n": 9, "fail": True}, user="planner.a")
    assert r.status_code == 409 and r.json()["error"]["code"] == "conflict"
    assert all(row["input"].get("n") != 9 for row in journal("test.act"))


def test_agent_gate(test_actions):
    prep = {"X-Circularity-Preparer": "finder"}
    r = call("test.commit", {}, **prep)
    assert r.status_code == 403 and r.json()["error"]["code"] == "approval_required"
    assert call("test.commit", {}, **prep, **{"X-Circularity-Confirmed": "true"}).status_code == 200
    r = call(
        "decision.approve",
        {"case_id": "RT-1048", "rationale": "Agent says approve this one.", "reviewed": True},
        user="approver",
        **prep,
        **{"X-Circularity-Confirmed": "true"},
    )
    assert (
        r.json()["error"]["message"] == "Decisions are approved, overridden or declined only in the approval card, by a person."
    )
    assert journal("test.commit")[-1]["preparer"] == "finder"


def test_journal_endpoint_respects_tenants(test_actions):
    call("test.act", {"case_id": "RT-1048", "n": 3}, user="planner.a")
    mine = client.get("/api/journal", headers=h("planner.a")).json()
    assert any(r["case_id"] == "RT-1048" for r in mine)
    theirs = client.get("/api/journal", headers=h("planner.b")).json()
    assert all(r["case_id"] != "RT-1048" for r in theirs)

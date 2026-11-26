"""Plan 3 task 3: the real resources under /api/v1 (di.resources.*): list and get scoped per account, the writes that go
through the action pipeline (same action ids as the UI, so the journal shows them), and 405 with a reason elsewhere."""

import pytest

from di.resources import REGISTRY
from tests.helpers import client, h

NAMES = {
    "cases", "my-tasks", "sources", "conflicts", "instructions", "workflows", "workflow-runs", "notes", "comments",
    "scenarios", "requests", "mcp-servers", "accounts", "identity-mappings", "journal",
}  # fmt: skip
ROOT = "/api/v1/"


def get(path, user="admin", **params):
    return client.get(ROOT + path, params=params, headers=h(user))


@pytest.fixture
def calls(monkeypatch):
    """Stand-in for the pipeline in dispatch tests: record (action, input), answer ok."""
    seen: list[tuple[str, dict]] = []

    def fake(action, body, ctx):
        seen.append((action, body))
        return {"ok": True, "output": {"echo": body}}

    monkeypatch.setattr("di.resources.router.invoke", fake)
    return seen


def test_every_group_is_registered_with_fields_or_a_reason():
    assert set(REGISTRY) >= NAMES
    for n in NAMES:
        r = REGISTRY[n]
        for verb in ("create", "update", "delete"):
            if not getattr(r, verb) and not (verb == "update" and r.update_actions):
                assert r.why_not.get(verb), f"{n} has no {verb} and no reason"


# ---------------------------------------------------------------- cases and my-tasks
def test_cases_list_is_scoped_to_the_tenant():
    b = get("cases", "planner.b", limit=500).json()["items"]
    assert b and {c["owner"] for c in b} == {"Customer B"} and "RT-1048" not in {c["id"] for c in b}
    a = get("cases", "planner.a", limit=500).json()["items"]
    assert "RT-1048" in {c["id"] for c in a}


def test_a_case_of_another_tenant_is_403_tenant_boundary():
    r = get("cases/RT-1048", "planner.b")
    assert r.status_code == 403 and r.json()["error"]["code"] == "tenant_boundary"
    assert get("cases/RT-1048", "planner.a").json()["id"] == "RT-1048"
    assert get("cases/RT-0000").status_code == 404


def test_cases_take_filters_and_page():
    rows = get("cases", "admin", owner="Customer C", limit=5).json()
    assert rows["items"] and {c["owner"] for c in rows["items"]} == {"Customer C"} and rows["next_cursor"] == "5"


def test_cases_have_no_create_or_delete_and_say_why():
    for verb, call in (("POST", client.post), ("DELETE", client.delete)):
        url = ROOT + "cases" + ("/RT-1048" if verb == "DELETE" else "")
        r = call(url, **({"json": {}} if verb == "POST" else {}), headers=h("admin"))
        assert r.status_code == 405 and r.json()["error"]["code"] == "not_supported" and r.json()["error"]["message"]


def test_case_patch_runs_the_decision_action_and_checks_its_fields(calls):
    r = client.patch(
        ROOT + "cases/RT-1048", json={"action": "approve", "rationale": "x" * 20, "reviewed": True}, headers=h("admin")
    )
    assert r.status_code == 200 and calls == [
        ("decision.approve", {"rationale": "x" * 20, "reviewed": True, "case_id": "RT-1048"})
    ]
    r = client.patch(ROOT + "cases/RT-1048", json={"action": "approve", "colour": "red"}, headers=h("admin"))
    assert r.status_code == 422 and "colour" in r.json()["error"]["message"] and len(calls) == 1
    r = client.patch(ROOT + "cases/RT-1048", json={"action": "bogus"}, headers=h("admin"))
    assert r.status_code == 422 and "approve" in r.json()["error"]["message"]
    r = client.patch(ROOT + "cases/RT-1048", json={"rationale": "x"}, headers=h("admin"))
    assert r.status_code == 422 and len(calls) == 1


def test_a_case_patch_by_another_tenant_never_reaches_the_pipeline(calls):
    r = client.patch(ROOT + "cases/RT-1048", json={"action": "submit"}, headers=h("planner.b"))
    assert r.status_code == 403 and calls == []


def test_my_tasks_is_read_only_and_per_account():
    r = get("my-tasks", "approver")
    assert r.status_code == 200 and isinstance(r.json()["items"], list)
    assert client.post(ROOT + "my-tasks", json={}, headers=h("approver")).status_code == 405


# ---------------------------------------------------------------- sources, conflicts, instructions
def test_sources_list_get_and_who_may_see_them():
    rows = get("sources").json()["items"]
    assert rows and {"id", "name"} <= set(rows[0])
    sid = rows[0]["id"]
    assert get(f"sources/{sid}").json()["id"] == sid
    assert get("sources", "planner.a").status_code == 403
    assert get("sources/nope").status_code == 404


def test_sources_write_through_their_actions(calls):
    """The sync verb keeps the stand-in (it reads the shared source-sim); the others are real pipeline calls below."""
    sid = get("sources").json()["items"][0]["id"]
    assert client.patch(ROOT + f"sources/{sid}", json={"action": "sync"}, headers=h("admin")).status_code == 200
    assert calls == [("source.sync", {"source_id": sid})]


def test_sources_connect_pause_resume_rotate_update_delete_for_real():
    from tests.test_source_connect import CAT, _cleanup

    _cleanup()
    try:
        r = client.post(ROOT + "sources", json={"catalog": CAT, "auth": "key", "scopes": ["read"]}, headers=h("admin"))
        assert r.status_code == 201 and r.json()["source_id"] == CAT, r.text
        for action, extra in (
            ("pause", {}),
            ("resume", {}),
            ("rotate", {"days": 30, "secret": "a-new-secret-1"}),
            ("reconnect", {}),
        ):
            r = client.patch(ROOT + f"sources/{CAT}", json={"action": action, **extra}, headers=h("admin"))
            assert r.status_code == 200, (action, r.text)
        body = {"mode": "edit", "d": {"method": "api", "name": "Workday renamed"}, "maps": [], "ops": {}, "note": "n"}
        r = client.patch(ROOT + f"sources/{CAT}", json=body, headers=h("admin"))
        assert r.status_code == 200 and "display name" in r.json()["changes"], r.text
        assert client.delete(ROOT + f"sources/{CAT}", headers=h("admin")).status_code == 200
        assert client.get(ROOT + f"sources/{CAT}", headers=h("admin")).status_code == 404
        journal = get("journal", limit=60).json()["items"]
        seen = {e.get("action") for e in journal}
        assert {"source.connect", "source.pause", "source.resume", "credentials.rotate", "source.delete"} <= seen
    finally:
        _cleanup()


def test_conflicts_read_and_patch(calls):
    from sqlalchemy import text

    from di.core.db import SessionLocal

    with SessionLocal() as s:  # a fresh database has none; the synced stack has hundreds
        cid = "CF-" + str(
            s.execute(
                text(
                    'INSERT INTO conflict (model, key, field, "values", status, opened_at) '
                    "VALUES ('asset', 'probe-asset', 'x_10_probe', CAST('{}' AS jsonb), 'open', now()) RETURNING id"
                )
            ).scalar_one()
        )
        s.commit()
    try:
        body = get("conflicts", status="all", limit=500).json()
        assert cid in {c["id"] for c in body["items"]}
        assert get(f"conflicts/{cid}").json()["id"] == cid
        assert get("conflicts", status="resolved", limit=500).json()["items"] == [] or cid not in {
            c["id"] for c in get("conflicts", status="resolved", limit=500).json()["items"]
        }
        assert get("conflicts", status="bogus").status_code == 422
        assert (
            client.patch(ROOT + f"conflicts/{cid}", json={"action": "resolve", "reason": "r"}, headers=h("admin")).status_code
            == 200
        )
        assert client.patch(ROOT + f"conflicts/{cid}", json={"action": "escalate"}, headers=h("admin")).status_code == 200
        assert [c[0] for c in calls] == ["conflict.resolve", "conflict.escalate"] and calls[0][1]["id"] == cid
        assert client.post(ROOT + "conflicts", json={}, headers=h("admin")).status_code == 405
        assert get("conflicts", "planner.a").status_code == 403
    finally:
        with SessionLocal() as s:
            s.execute(text("DELETE FROM conflict WHERE key = 'probe-asset'"))
            s.commit()


def test_instructions_are_scoped_to_visible_cases_and_resend(calls):
    rows = get("instructions", limit=500).json()["items"]
    mine = get("instructions", "planner.b", limit=500).json()["items"]
    assert {r["case_id"] for r in mine} <= {c["id"] for c in get("cases", "planner.b", limit=500).json()["items"]}
    assert len(mine) <= len(rows)
    if rows:
        r = rows[0]
        assert client.patch(ROOT + f"instructions/{r['id']}", json={"action": "resend"}, headers=h("admin")).status_code == 200
        assert calls == [("instruction.resend", {"case_id": r["case_id"]})]
    assert client.delete(ROOT + "instructions/1", headers=h("admin")).status_code == 405


# ---------------------------------------------------------------- workflows and runs
def test_workflows_list_get_and_crud_actions(calls):
    rows = get("workflows", limit=50).json()["items"]
    assert rows
    wid = rows[0]["id"]
    assert get(f"workflows/{wid}").json()["id"] == wid
    assert get("workflows/WF-NOPE").status_code == 404
    assert client.post(ROOT + "workflows", json={"name": "n"}, headers=h("admin")).status_code == 201
    assert client.patch(ROOT + f"workflows/{wid}", json={"name": "m"}, headers=h("admin")).status_code == 200
    assert client.patch(ROOT + f"workflows/{wid}", json={"action": "publish"}, headers=h("admin")).status_code == 200
    assert client.delete(ROOT + f"workflows/{wid}", headers=h("admin")).status_code == 200
    assert [c[0] for c in calls] == ["workflow.create", "workflow.save", "workflow.publish", "workflow.delete"]
    assert calls[1][1] == {"name": "m", "id": wid} and calls[3][1] == {"id": wid}


def test_workflows_are_hidden_from_a_role_without_the_studio():
    assert get("workflows", "planner.a").status_code == 403
    assert get("workflow-runs", "planner.a").status_code == 403
    assert get("workflows/WF-101", "planner.a").status_code == 403


def test_workflow_runs_are_read_with_a_filter_and_run_through_workflow_run():
    wid = get("workflows").json()["items"][0]["id"]
    runs = get("workflow-runs", workflow=wid, limit=5).json()["items"]
    assert all(r["workflow"] == wid for r in runs)
    if runs:
        assert get(f"workflow-runs/{runs[0]['id']}").status_code == 200
    r = client.post(ROOT + "workflow-runs", json={"id": wid}, headers=h("admin"))
    assert r.status_code == 201, r.text  # the real workflow.run: a run is started and journaled
    assert any(e.get("action") == "workflow.run" for e in get("journal", limit=20).json()["items"])
    assert client.delete(ROOT + "workflow-runs/RUN-1", headers=h("admin")).status_code in (404, 405)


# ---------------------------------------------------------------- state collections
def journal_actions(user="admin"):
    return [e["action"] for e in client.get("/api/journal", params={"limit": 50}, headers=h(user)).json()]


def test_a_note_is_sent_listed_for_its_recipient_and_acknowledged():
    body = {"ex_id": "var:Delayed approval", "to": "approver", "title": "Look at this", "msg": "Please look.", "sev": "High"}
    r = client.post(ROOT + "notes", json=body, headers=h("exec"))
    assert r.status_code == 201, r.text
    nid = r.json()["id"]
    assert "notify.send" in journal_actions("exec")
    assert nid in {n["id"] for n in get("notes", "approver").json()["items"]}
    assert nid not in {n["id"] for n in get("notes", "planner.a").json()["items"]}
    assert get(f"notes/{nid}", "planner.a").status_code in (403, 404)
    r = client.patch(ROOT + f"notes/{nid}", json={}, headers=h("approver"))
    assert r.status_code == 200, r.text
    assert get(f"notes/{nid}", "approver").json()["status"] == "ack" and "notify.acknowledge" in journal_actions("approver")
    assert client.delete(ROOT + f"notes/{nid}", headers=h("approver")).status_code == 405


def test_comments_are_added_and_read_by_key_and_never_edited():
    r = client.post(ROOT + "comments", json={"key": "src:erp", "text": "Looks fine"}, headers=h("admin"))
    assert r.status_code == 201, r.text
    assert "comment.add" in journal_actions()
    rows = get("comments", key="src:erp").json()["items"]
    assert rows and rows[-1]["text"] == "Looks fine" and rows[-1]["id"].startswith("CM-")
    assert get("comments", "planner.a", key="src:erp").json()["items"] == []
    assert client.patch(ROOT + f"comments/{rows[-1]['id']}", json={"text": "x"}, headers=h("admin")).status_code == 405


def test_scenarios_are_saved_listed_and_deleted_per_case():
    body = {"case_id": "RT-1048", "name": "Plan a", "scen": {"cost": 1}}
    r = client.post(ROOT + "scenarios", json=body, headers=h("planner.a"))
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    assert sid in {s["id"] for s in get("scenarios", "planner.a", case_id="RT-1048").json()["items"]}
    assert get("scenarios", "planner.b", case_id="RT-1048").json()["items"] == []
    assert get(f"scenarios/{sid}", "planner.b").status_code in (403, 404)
    assert client.delete(ROOT + f"scenarios/{sid}", headers=h("planner.b")).status_code in (403, 404)
    assert client.delete(ROOT + f"scenarios/{sid}", headers=h("planner.a")).status_code == 200
    assert sid not in {s["id"] for s in get("scenarios", "planner.a").json()["items"]}
    assert "scenario.delete" in journal_actions("planner.a")
    assert client.patch(ROOT + f"scenarios/{sid}", json={}, headers=h("planner.a")).status_code == 405


def test_requests_are_listed_by_who_may_see_them_and_decided_through_the_action(calls):
    admin = get("requests").json()["items"]
    assert {r["id"] for r in admin} >= {"REQ-301", "REQ-304"}
    assert "REQ-301" not in {r["id"] for r in get("requests", "planner.a").json()["items"]}
    assert get("requests/REQ-301").json()["kind"] == "mcp"
    assert get("requests", kind="tenant").json()["items"] and all(
        r["kind"] == "tenant" for r in get("requests", kind="tenant").json()["items"]
    )
    r = client.patch(ROOT + "requests/REQ-304", json={"decision": "approve", "note": "ok"}, headers=h("admin"))
    assert r.status_code == 200 and calls == [("access.decideRequest", {"decision": "approve", "note": "ok", "id": "REQ-304"})]
    assert client.post(ROOT + "requests", json={"tenant": "Customer A", "reason": "r"}, headers=h("admin")).status_code == 201
    assert calls[1][0] == "access.requestTenant"
    assert client.delete(ROOT + "requests/REQ-304", headers=h("admin")).status_code == 405


def test_mcp_servers_list_and_propose(calls):
    rows = get("mcp-servers").json()["items"]
    assert rows and get(f"mcp-servers/{rows[0]['id']}").status_code == 200
    assert get("mcp-servers", "planner.a").status_code == 403
    assert client.post(ROOT + "mcp-servers", json={"name": "A server"}, headers=h("developer")).status_code == 201
    assert calls == [("mcp.propose", {"name": "A server"})]
    assert client.delete(ROOT + f"mcp-servers/{rows[0]['id']}", headers=h("admin")).status_code == 405


# ---------------------------------------------------------------- accounts, identity mappings, journal
def test_accounts_and_identity_mappings_are_for_admin(calls):
    accts = get("accounts").json()["items"]
    assert {"admin", "planner-a"} <= {a["id"] for a in accts}
    assert get("accounts/planner-a").json()["role"] == "Planner"
    assert get("accounts", "planner.a").status_code == 403
    users = get("identity-mappings").json()["items"]
    assert users
    uid = users[0]["id"]
    assert get(f"identity-mappings/{uid}").json()["id"] == uid
    assert get("identity-mappings", "planner.a").status_code == 403
    r = client.patch(ROOT + f"identity-mappings/{uid}", json={"field": "role", "value": "Planner"}, headers=h("admin"))
    assert r.status_code == 200 and calls[0] == ("access.mapIdentity", {"field": "role", "value": "Planner", "acct": uid})
    assert client.delete(ROOT + f"identity-mappings/{uid}", headers=h("admin")).status_code == 200
    assert calls[1] == ("access.removeUser", {"id": uid})
    assert client.delete(ROOT + "accounts/planner-a", headers=h("admin")).status_code == 405
    assert client.post(ROOT + "accounts", json={}, headers=h("admin")).status_code == 405


def test_the_journal_is_read_only_and_scoped():
    client.post(ROOT + "comments", json={"key": "src:erp", "text": "journal probe"}, headers=h("admin"))
    rows = get("journal", limit=5).json()["items"]
    assert rows and rows[0]["action"] == "comment.add" and rows[0]["id"] == rows[0]["seq"]
    assert get(f"journal/{rows[0]['seq']}").json()["action"] == "comment.add"
    assert get("journal/999999999").status_code == 404
    for method, url in (("POST", ROOT + "journal"), ("PATCH", ROOT + "journal/1"), ("DELETE", ROOT + "journal/1")):
        r = client.request(method, url, json={}, headers=h("admin"))
        assert r.status_code == 405 and r.json()["error"]["message"]
    assert get("journal", "planner.b", case_id="RT-1048").json()["items"] == []

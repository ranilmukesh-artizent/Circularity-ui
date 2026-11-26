"""P9-8.1 (registry entry I-18; story X-10 enabler, 01 section 2; R21): the adapter registry, connections that start in
test, and the system owner's approval of production access and of write-back.

A connection is a new approvable object: the person who asks for production or write access cannot approve it, no agent
creates, requests, approves, declines or promotes one, and an owner outside the source's org unit is refused. The
module removes the sources, approvals, work items and registry rows it made, so the demo's seeded state is what the
parity tests that run after see.
"""
# ruff: noqa: E501 - long lines in the SQL and the call bodies

import json

import pytest
from sqlalchemy import text

from di.connectors import lifecycle, registry
from di.core import policy
from di.core.auth import load_context
from di.core.db import SessionLocal, engine
from di.services.actions.pipeline import Actor, CallContext, invoke
from di.services.agents.forbidden import FORBIDDEN_ACTIONS, forbidden
from di.services.cases import store as case_store
from di.services.instructions import queue, send, writers
from tests import starting
from tests.helpers import call

SECRET = "s3cr3t-value-123"
MAKER_CHECKER = "Maker-checker: you asked for this connection, so the system owner must approve it."
NEW_SECRET = "prod-key-98765"


def _clean() -> None:
    with engine.begin() as c:
        made = list(c.execute(text("SELECT source_id FROM source_connection WHERE registry_id IS NOT NULL")).scalars())
        for t in ("sync_run", "fetch_log", "raw_record", "sync_cursor", "source_connection", "source_secret", "field_mapping"):
            c.execute(text(f"DELETE FROM {t} WHERE source_id = ANY(:i)"), {"i": made})  # noqa: S608 - fixed names
        c.execute(text("DELETE FROM source_system WHERE id = ANY(:i)"), {"i": made})
        c.execute(text("DELETE FROM instruction WHERE system = ANY(:i)"), {"i": made})
        c.execute(text("DELETE FROM connection_approval"))
        c.execute(text("DELETE FROM work_item WHERE type LIKE 'connection_approval%'"))
        c.execute(text("DELETE FROM adapter_registry"))
        c.execute(text("DELETE FROM job WHERE kind = 'sync.source'"))


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    _clean()
    yield
    _clean()
    starting.reset()


# ---------------------------------------------------------------- helpers
def ok(r: dict) -> dict:
    assert r.get("ok"), r
    return r["output"]


def refused(r: dict, code: str) -> str:
    assert r.get("ok") is False and r["error"]["code"] == code, r
    return r["error"]["message"]


def create(owner: str = "approver", org: str = "Customer A", secret: str | None = None, user: str = "developer") -> dict:
    body = {"registry_id": "workday", "version": 1, "name": "Workday test", "org_unit_id": org, "system_owner": owner}
    if secret:
        body["secret"] = secret
    return call("connection.create", body, user)


def request(sid: str, env: str = "production", access: str = "read", user: str = "developer") -> dict:
    return call("connection.requestOwner", {"source_id": sid, "environment": env, "access": access}, user)


def env_of(sid: str) -> str | None:
    with engine.connect() as c:
        return c.execute(text("SELECT environment FROM source_connection WHERE source_id = :i"), {"i": sid}).scalar()


def queued(sid: str) -> int:
    with engine.connect() as c:
        return int(
            c.execute(
                text("SELECT count(*) FROM job WHERE kind = 'sync.source' AND payload->>'source_id' = :i"), {"i": sid}
            ).scalar_one()
        )


@pytest.fixture
def instruction():
    """An `order` instruction for `workday` on a case's current approval (removed by `fresh`)."""

    def make(system: str = "workday") -> int:
        with SessionLocal() as s:
            c = next(x for x in case_store.all_cases(s) if x.get("exec"))
            ref = c["exec"]["ref"]
            step = len(c["exec"]["steps"]) + 70
            iid = s.execute(
                text(
                    "INSERT INTO instruction (case_id, approval_ref, step, kind, system, idem_key, match_refs, queued_at) "
                    "VALUES (:c, :r, :n, 'order', :sys, :k, '[]'::jsonb, now()) RETURNING id"
                ),
                {"c": c["id"], "r": ref, "n": step, "sys": system, "k": f"{ref}.{step}.order.{system}"},
            ).scalar_one()
            s.commit()
        return int(iid)

    return make


def fake_writer(seen: list):
    def w(s, ins, c, prev):
        seen.append(ins["kind"])
        return writers.Sent([{"call": "fake", "body": {}}], "DOC-1")

    return w


def promote_ready(sid: str, access: str = "read") -> int:
    """An approved request for production access; the owner is `approver`, the requester `developer`."""
    rid = ok(request(sid, "production", access))["id"]
    ok(call("connection.ownerApprove", {"id": rid}, "approver"))
    return int(rid)


# ---------------------------------------------------------------- the registry
def test_registry_catalogue_entries_are_pure_and_hold_no_secret():
    entries = registry.catalogue_entries()
    by_kind = {k: [e for e in entries if e.kind == k] for k in ("catalogue", "generic_rest", "from_spec")}
    assert len(by_kind["catalogue"]) >= 15 and all(e.status == "released" for e in by_kind["catalogue"])
    assert [e.id for e in by_kind["generic_rest"]] == ["generic-rest"] and not by_kind["from_spec"]
    assert by_kind["generic_rest"][0].auth_methods == ("none", "api_key", "bearer", "basic", "oauth_cc")
    assert "demo-secret" not in json.dumps([e.spec for e in entries]) and "demo_secret" not in json.dumps(
        [e.spec for e in entries]
    )
    assert registry.access_of("Read") == "read" and registry.access_of("Read / write") == "read_write"
    assert registry.access_of("Write only?") == "read"


def test_registry_lists_three_kinds():
    out = ok(call("registry.list", {}, "developer"))
    kinds = [e["kind"] for e in out["entries"]]
    assert kinds.count("catalogue") >= 15 and kinds.count("generic_rest") == 1 and "from_spec" not in kinds
    assert all(e["status"] == "released" for e in out["entries"])
    only = ok(call("registry.list", {"kind": "generic_rest"}, "developer"))
    assert [e["id"] for e in only["entries"]] == ["generic-rest"]
    assert call("registry.list", {}, "planner-b")["error"]["code"] == "out_of_scope"


def test_registry_save_entry_makes_a_draft_and_refuses_the_catalogue():
    entry = {"id": "acme-api", "kind": "from_spec", "system_type": "erp", "vendor_family": "Acme", "auth_methods": ["api_key"]}
    out = ok(call("registry.saveEntry", {"entry": entry}, "developer"))
    assert (out["id"], out["version"], out["status"]) == ("acme-api", 1, "draft")
    again = ok(call("registry.saveEntry", {"entry": entry}, "developer"))
    assert again["version"] == 2
    kinds = [e["id"] for e in ok(call("registry.list", {"kind": "from_spec"}, "developer"))["entries"]]
    assert kinds == ["acme-api", "acme-api"]  # the org's own drafts show to the person who saved them
    msg = refused(
        call("registry.saveEntry", {"entry": {**entry, "id": "w", "kind": "catalogue"}}, "developer"), "validation_error"
    )
    assert msg == "Catalogue connectors are maintained by Circularity."


def test_a_draft_without_an_org_unit_can_start_a_connection_at_any_org():
    """The smoke P9-8.22 found it: an imported spec's draft has no org unit, the picker lists it, and creating the
    connection at the chosen org said "No connector ... in the registry"."""
    entry = {"id": "nolocal-api", "kind": "from_spec", "system_type": "erp", "vendor_family": "Acme", "auth_methods": ["basic"]}
    ok(call("registry.saveEntry", {"entry": entry}, "developer"))
    ids = [e["id"] for e in ok(call("registry.list", {"kind": "from_spec", "org_unit_id": "Customer A"}, "developer"))["entries"]]
    assert "nolocal-api" in ids
    body = {"registry_id": "nolocal-api", "version": 1, "name": "No local", "org_unit_id": "Customer A", "system_owner": "approver",
            "test_base_url": "http://source-sim:8100/x"}  # fmt: skip
    ok(call("connection.create", body, "developer"))


def test_registry_release_maker_cannot_release():
    entry = {"id": "acme-api", "kind": "from_spec", "system_type": "erp", "vendor_family": "Acme"}
    ok(call("registry.saveEntry", {"entry": entry}, "developer"))
    refused(call("registry.release", {"id": "acme-api", "version": 1}, "admin"), "conflict")  # a draft is not tested yet
    with engine.begin() as c:
        c.execute(text("UPDATE adapter_registry SET status = 'tested' WHERE id = 'acme-api'"))
    msg = refused(call("registry.release", {"id": "acme-api", "version": 1}, "developer"), "conflict")
    assert msg == "Maker-checker: you drafted this connector, so another person must release it."
    assert ok(call("registry.release", {"id": "acme-api", "version": 1}, "admin"))["status"] == "released"


# ---------------------------------------------------------------- a connection starts in test
def test_connection_starts_in_test():
    out = ok(create())
    sid = out["source_id"]
    assert sid == "workday" and (out["environment"], out["access"]) == ("test", "read")
    assert env_of(sid) == "test" and queued(sid) == 0
    with SessionLocal() as s:
        cfg = lifecycle.config(s, sid)
        assert (cfg["env"], cfg["rw"]) == ("Test", "Read") and lifecycle.access_of(s, sid) == "read"
        from di.connectors import connection, sync

        conn = connection.connection_for(s, sid)
        assert conn is not None and (conn.environment, conn.system_owner) == ("test", "approver")
        assert (conn.registry_id, conn.registry_version) == ("workday", 1)
        assert sync.enqueue_sync(s, sid, "manual") is None and sid not in sync.enqueue_due(s)
        assert sync.run_sync(sid)["status"] == "skipped"
    assert queued(sid) == 0


def test_connection_from_generic_rest_needs_a_url_and_starts_in_test():
    body = {
        "registry_id": "generic-rest",
        "version": 1,
        "name": "Parts API",
        "org_unit_id": "Customer A",
        "system_owner": "approver",
    }
    msg = refused(call("connection.create", body, "developer"), "validation_error")
    assert "base URL" in msg
    out = ok(call("connection.create", body | {"test_base_url": "https://parts.example.test/api"}, "developer"))
    assert env_of(out["source_id"]) == "test" and queued(out["source_id"]) == 0


def test_connection_needs_a_directory_owner_and_a_known_entry():
    body = {"registry_id": "workday", "version": 1, "name": "W", "org_unit_id": "Customer A"}
    assert refused(call("connection.create", body, "developer"), "validation_error") == (
        "Name the system owner: a person from the directory."
    )
    refused(call("connection.create", body | {"system_owner": "nobody-here"}, "developer"), "validation_error")
    refused(call("connection.create", body | {"system_owner": "approver", "registry_id": "nope"}, "developer"), "not_found")
    assert call("connection.create", body | {"system_owner": "approver"}, "planner-b")["error"]["code"] == "out_of_scope"


def test_test_connection_gets_no_instructions(monkeypatch, instruction):
    sid = ok(create())["source_id"]
    seen: list = []
    monkeypatch.setitem(writers.WRITERS, "order", fake_writer(seen))
    iid = instruction(sid)
    assert send.send(iid) == "failed" and seen == []
    with SessionLocal() as s:
        row = queue.get(s, iid)
    assert "test environment" in row["last_error"] and "Workday" in row["last_error"]


def test_promote_needs_owner_approval():
    sid = ok(create())["source_id"]
    msg = refused(call("connection.promote", {"source_id": sid, "secret": NEW_SECRET}, "developer"), "conflict")
    assert msg == "The system owner has not approved production access for Workday test."
    rid = ok(request(sid))["id"]
    refused(call("connection.promote", {"source_id": sid, "secret": NEW_SECRET}, "developer"), "conflict")  # still pending
    ok(call("connection.ownerApprove", {"id": rid}, "approver"))
    out = ok(call("connection.promote", {"source_id": sid, "secret": NEW_SECRET}, "developer"))
    assert out["environment"] == "production" and env_of(sid) == "production" and queued(sid) == 1
    with SessionLocal() as s:
        assert lifecycle.config(s, sid)["env"] == "Production"
        n = s.execute(text("SELECT max(version) FROM source_secret WHERE source_id = :i AND kind = 'auth'"), {"i": sid}).scalar()
        assert n == 2  # the catalogue's synthetic key at create, then the production key


def test_owner_decline_needs_a_reason_and_blocks_promotion():
    sid = ok(create())["source_id"]
    rid = ok(request(sid))["id"]
    refused(call("connection.ownerDecline", {"id": rid, "reason": "too short"}, "approver"), "validation_error")
    ok(call("connection.ownerDecline", {"id": rid, "reason": "Not until the audit is finished."}, "approver"))
    refused(call("connection.promote", {"source_id": sid, "secret": NEW_SECRET}, "developer"), "conflict")
    refused(call("connection.ownerApprove", {"id": rid}, "approver"), "conflict")  # already decided
    ok(request(sid))  # a new request after a decline is allowed


def test_identical_pending_request_is_a_conflict_and_opens_one_work_item():
    sid = ok(create())["source_id"]
    ok(request(sid))
    refused(request(sid), "conflict")
    with engine.connect() as c:
        n = c.execute(
            text(
                "SELECT count(*) FROM work_item WHERE type LIKE 'connection_approval%' AND status = 'open' AND owner_account = 'approver'"
            )
        ).scalar()
    assert n == 1


def test_owner_decision_closes_the_my_work_item():
    sid = ok(create())["source_id"]
    rid = ok(request(sid))["id"]
    ok(call("connection.ownerApprove", {"id": rid}, "approver"))
    with engine.connect() as c:
        st = c.execute(text("SELECT status FROM work_item WHERE type = :t"), {"t": f"connection_approval:{rid}"}).scalar()
    assert st == "done"


def test_write_back_needs_second_approval(monkeypatch, instruction):
    sid = ok(create())["source_id"]
    promote_ready(sid)
    ok(call("connection.promote", {"source_id": sid, "secret": NEW_SECRET}, "developer"))
    seen: list = []
    monkeypatch.setitem(writers.WRITERS, "order", fake_writer(seen))
    iid = instruction(sid)
    assert send.send(iid) == "failed" and seen == []
    with SessionLocal() as s:
        assert "read-only" in queue.get(s, iid)["last_error"]
    promote_ready(sid, "read_write")
    with SessionLocal() as s:
        assert lifecycle.config(s, sid)["rw"] == "Read / write" and lifecycle.access_of(s, sid) == "read_write"
    assert send.send(iid, resend=True) == "sent" and seen == ["order"]


def test_connection_maker_cannot_approve():
    sid = ok(create(owner="approver"))["source_id"]
    rid = ok(request(sid, user="admin"))["id"]
    assert refused(call("connection.ownerApprove", {"id": rid}, "admin"), "conflict") == MAKER_CHECKER
    refused(call("connection.ownerDecline", {"id": rid, "reason": "I would rather not have asked."}, "admin"), "conflict")
    # the requester named as the owner is refused as well
    with engine.begin() as c:
        c.execute(text("UPDATE source_connection SET system_owner = 'developer' WHERE source_id = :i"), {"i": sid})
        c.execute(text("DELETE FROM connection_approval"))
    rid = ok(request(sid, user="developer"))["id"]
    assert refused(call("connection.ownerApprove", {"id": rid}, "developer"), "conflict") == MAKER_CHECKER
    # someone who is neither the owner nor an Admin cannot decide it
    assert call("connection.ownerApprove", {"id": rid}, "planner-a")["error"]["code"] == "out_of_scope"
    # an Admin who did not ask can
    assert ok(call("connection.ownerApprove", {"id": rid}, "admin"))["status"] == "approved"


AGENT_CALLS = (
    (
        "connection.create",
        {"registry_id": "workday", "version": 1, "name": "W", "org_unit_id": "Customer A", "system_owner": "approver"},
    ),
    ("connection.requestOwner", {"source_id": "workday", "environment": "production", "access": "read"}),
    ("connection.ownerApprove", {"id": 1}),
    ("connection.ownerDecline", {"id": 1, "reason": "An agent may not decline."}),
    ("connection.promote", {"source_id": "workday", "secret": NEW_SECRET}),
    ("registry.release", {"id": "acme-api", "version": 1}),
)


def test_connection_agent_cannot_owner_approve():
    for action, _ in AGENT_CALLS:
        assert forbidden(action) and action not in ("registry.saveEntry", "registry.list")
    assert "connection." in FORBIDDEN_ACTIONS and "registry.release" in FORBIDDEN_ACTIONS
    for action, body in AGENT_CALLS:
        for confirmed in (False, True):
            with SessionLocal() as s:
                pctx = load_context(s)
                ctx = CallContext(
                    actor=Actor(account=policy.account("admin", pctx), ctx=pctx), session=s,
                    preparer="integration-assistant", confirmed=confirmed,
                )  # fmt: skip
                r = invoke(action, body, ctx)
                s.rollback()
            assert r["ok"] is False and r["error"]["code"] == "approval_required", (action, confirmed, r)
    assert env_of("workday") is None  # nothing was created


def test_agents_may_read_the_registry_and_draft_an_entry():
    for action, body in (
        ("registry.list", {}),
        ("registry.saveEntry", {"entry": {"id": "acme-api", "kind": "from_spec", "system_type": "erp", "vendor_family": "Acme"}}),
    ):
        assert not forbidden(action)
        with SessionLocal() as s:
            pctx = load_context(s)
            ctx = CallContext(
                actor=Actor(account=policy.account("developer", pctx), ctx=pctx), session=s, preparer="assembler"
            )  # fmt: skip
            r = invoke(action, body, ctx)
            s.commit()
        assert r["ok"] is True or r["error"]["code"] == "held", (action, r)  # a draft is configuration, never code


def test_connection_tenant_boundary():
    msg = refused(create(owner="planner-b", org="Customer A", user="admin"), "tenant_boundary")
    assert "Customer A" in msg
    assert env_of("workday") is None
    # the owner sees the org: allowed
    assert ok(create(owner="planner-a", org="Customer A", user="admin"))["source_id"] == "workday"


def test_connection_approvals_is_a_read_for_managers_and_the_named_owner():
    sid = ok(create())["source_id"]
    rid = ok(request(sid, "production", "read_write"))["id"]
    for user in ("developer", "approver"):
        out = ok(call("connection.approvals", {"source_id": sid}, user))
        assert out["environment"] == "test" and out["access"] == "read" and out["system_owner"] == "approver"
        assert [(a["id"], a["status"], a["access"]) for a in out["approvals"]] == [(rid, "pending", "read_write")]
    assert call("connection.approvals", {"source_id": sid}, "planner-a")["error"]["code"] == "out_of_scope"


def test_secret_never_returned():
    out = create(secret=SECRET)
    sid = ok(out)["source_id"]
    rid = ok(request(sid))["id"]
    seen = [
        json.dumps(out),
        json.dumps(call("registry.list", {}, "developer")),
        json.dumps(call("connection.approvals", {"source_id": sid}, "developer")),
        json.dumps(call("connection.ownerApprove", {"id": rid}, "approver")),
        json.dumps(call("connection.promote", {"source_id": sid, "secret": NEW_SECRET}, "developer")),
    ]
    assert all(SECRET not in t and NEW_SECRET not in t for t in seen)
    with engine.connect() as c:
        for table in ("action_journal", "connection_approval", "work_item", "source_connection", "adapter_registry"):
            rows = c.execute(text(f"SELECT t::text FROM {table} t")).scalars().all()  # noqa: S608 - fixed names
            assert not any(SECRET in r or NEW_SECRET in r for r in rows), table
        stored = c.execute(
            text("SELECT ciphertext, last4 FROM source_secret WHERE source_id = :i ORDER BY version"), {"i": sid}
        ).all()
    assert len(stored) == 2 and all(SECRET.encode() not in bytes(r[0]) and NEW_SECRET.encode() not in bytes(r[0]) for r in stored)


def test_the_demo_reset_removes_the_approvals_of_the_sources_it_removes():
    """Found by the smoke P9-8.22: a reset removed a connection's source but kept its approval, so the next source that
    got the same id read "Approved by engineer" before anyone had asked."""
    from di.connectors import sync

    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO source_system (id, vendor, type, status, interval_min, authority, owner) VALUES ('zz_reset_1', 'V', 'erp', 'live', 0, '{}', 'o')")
        )
        conn.execute(
            text("INSERT INTO connection_approval (source_id, environment, access, requested_by, owner, status, decided_by) VALUES ('zz_reset_1', 'production', 'read', 'developer', 'engineer', 'approved', 'engineer')")
        )
    try:
        with engine.begin() as conn:
            sync.reset_sources(conn)
        with engine.begin() as conn:
            assert conn.execute(text("SELECT count(*) FROM source_system WHERE id = 'zz_reset_1'")).scalar() == 0
            assert conn.execute(text("SELECT count(*) FROM connection_approval WHERE source_id = 'zz_reset_1'")).scalar() == 0
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM connection_approval WHERE source_id = 'zz_reset_1'"))
            conn.execute(text("DELETE FROM source_system WHERE id = 'zz_reset_1'"))

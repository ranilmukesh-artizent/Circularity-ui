"""Plan 9 P9-0.4: catalogue hygiene and credentials rotation forbidden to agents (review focus 6).

- credentials.rotate joins FORBIDDEN_ACTIONS: an agent that prepares it is refused, the stored secret is untouched
- mapping.revert and tables.update are HELD_FOR_PERSON: even an agent with autonomy "act" only proposes them
- source.test and source.sandboxKey (NO_AGENT_READS) handle a secret: no agent may call them
- the catalogue's agent_mode and the pipeline's agent_route agree for every action of the registry
- the twelve actions with no handler are "no" and not implemented; the seeded agents list none of them as a tool
"""

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import text

from di.connectors import mapping, secrets
from di.connectors.sync import ensure_sources
from di.core.db import SessionLocal
from di.mcp.tools import TOOLS
from di.services.actions.pipeline import SYSTEM, CallContext, agent_route
from di.services.actions.registry import ACTIONS
from di.services.agents.catalog import agent_mode, catalog
from tests import starting
from tests.helpers import call, client, h

AGENT = "coordinator"  # seeded, autonomy act
UNBUILT = (
    "analytics.query", "audit.search", "sources.health", "sources.diagnose", "mapping.suggest", "mapping.apply",
    "tables.suggestLinks", "tables.describe", "conflict.suggest", "import.clean", "event.explain", "asset.summary",
)  # fmt: skip
SID = "insp"


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    with SessionLocal() as s:
        ensure_sources(s)
        s.execute(text("DELETE FROM source_secret"))
        s.execute(text("DELETE FROM field_mapping WHERE source_id = :s"), {"s": SID})
        s.commit()
    yield
    with SessionLocal() as s:
        s.execute(text("DELETE FROM source_secret"))
        s.execute(text("DELETE FROM field_mapping WHERE source_id = :s"), {"s": SID})
        s.commit()
    starting.reset()


def prepared(action: str, body: dict, user: str = "admin", agent: str = AGENT) -> dict:
    hdr = h(user) | {"X-Circularity-Preparer": agent}
    return client.post(f"/api/actions/{action}", json=body, headers=hdr).json()


def proposals() -> list[dict]:
    with SessionLocal() as s:
        return [dict(r) for r in s.execute(text("SELECT agent, action, status FROM agent_proposal")).mappings()]


def test_agent_cannot_rotate_credentials():
    with SessionLocal() as s:
        secrets.put_secret(s, "erp", "auth", "original-secret-1", 90, "test")
        s.commit()
        before = [dict(r) for r in s.execute(text("SELECT * FROM source_secret WHERE source_id = 'erp'")).mappings()]
    body = {"source_id": "erp", "days": 30, "secret": "agent-chosen-secret-2"}
    for confirmed in (False, True):
        hdr = h("admin") | {"X-Circularity-Preparer": AGENT} | ({"X-Circularity-Confirmed": "true"} if confirmed else {})
        r = client.post("/api/actions/credentials.rotate", json=body, headers=hdr).json()
        assert r["ok"] is False and r["error"]["code"] == "approval_required", r
    with SessionLocal() as s:
        after = [dict(r) for r in s.execute(text("SELECT * FROM source_secret WHERE source_id = 'erp'")).mappings()]
    assert after == before
    assert proposals() == []
    # a person's rotation is unchanged
    assert call("credentials.rotate", body, "admin")["ok"] is True


def test_mapping_revert_held_for_agent_with_act():
    start = mapping.starting_maps(SID)
    edited = [list(m) for m in start]
    edited[0][4] = "code:grade"
    with SessionLocal() as s:
        assert mapping.save_version(s, SID, edited, "test") == 2
        s.commit()
        assert [v["version"] for v in mapping.versions(s, SID)] == [2, 1]
    r = prepared("mapping.revert", {"source_id": SID, "version": 1}, "developer")
    assert r["ok"] is True and set(r["output"]) == {"held"}, r
    with SessionLocal() as s:
        assert mapping.active_version(s, SID) == 2
    assert [(p["agent"], p["action"], p["status"]) for p in proposals()] == [(AGENT, "mapping.revert", "pending")]


def test_tables_update_held_for_agent_with_act():
    body = {"src": "erp", "op": "add", "table": {"n": "T001X", "cols": [["A", ""]], "rows": "—", "x": 1, "y": 1}}
    r = prepared("tables.update", body, "developer")
    assert r["ok"] is True and set(r["output"]) == {"held"}, r
    assert [(p["agent"], p["action"], p["status"]) for p in proposals()] == [(AGENT, "tables.update", "pending")]
    model = client.get("/api/screens/integration/tables", headers=h("developer")).json()
    assert "T001X" not in str(model)


def test_unimplemented_actions_not_agent_allowed():
    by = {t["action"]: t for t in catalog()}
    for a in UNBUILT:
        assert by[a]["agent_mode"] == "no" and by[a]["implemented"] is False and by[a]["agent_allowed"] is False, a
    assert by["case.evidence"]["implemented"] is True


def test_seeded_agents_list_no_unbuilt_tools():
    known = set(TOOLS)
    with SessionLocal() as s:
        rows = s.execute(text("SELECT id, tools FROM agent_identity")).all()
    for agent_id, tools in rows:
        for t in tools:
            assert t in known or (t in ACTIONS and ACTIONS[t].handler is not None), (agent_id, t)


def test_migration_0029_removes_unbuilt_tools_and_is_idempotent():
    path = Path(__file__).resolve().parents[1] / "migrations" / "versions" / "0029_agent_tools_hygiene.py"
    spec = importlib.util.spec_from_file_location("m0029", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    with SessionLocal() as s:
        s.execute(
            text("INSERT INTO agent_identity (id, name, kind, tools, autonomy) VALUES ('mig-test', 'M', 'external', :t, 'read')"),
            {"t": ["case.evidence", *mod.UNBUILT]},
        )
        for _ in range(2):
            s.execute(text(mod.SQL))
            assert s.execute(text("SELECT tools FROM agent_identity WHERE id = 'mig-test'")).scalar_one() == ["case.evidence"]
        s.execute(text("DELETE FROM agent_identity WHERE id = 'mig-test'"))
        s.commit()


def test_catalogue_agrees_with_pipeline():
    assert call("agent.register", {"id": "hygiene-act", "name": "Hygiene", "tools": [], "autonomy": "act"}, "admin")["ok"]
    try:
        with SessionLocal() as s:
            for a in ACTIONS.values():
                ctx = CallContext(actor=SYSTEM, session=s, preparer="hygiene-act", confirmed=True)
                assert (agent_route(a, ctx) == "refused") == (agent_mode(a) == "no"), a.id
                if a.risk in ("act", "draft"):
                    ctx = CallContext(actor=SYSTEM, session=s, preparer="hygiene-act", confirmed=False)
                    assert (agent_route(a, ctx) == "held") == (agent_mode(a) == "held"), a.id
    finally:
        with SessionLocal() as s:
            s.execute(text("DELETE FROM agent_identity WHERE id = 'hygiene-act'"))
            s.commit()


def test_reads_under_forbidden_prefix_show_allowed():
    by = {t["action"]: t for t in catalog()}
    assert by["access.lookup"]["agent_mode"] == "yes"
    assert by["source.test"]["agent_mode"] == "no" and by["source.sandboxKey"]["agent_mode"] == "no"
    assert by["mapping.revert"]["agent_mode"] == "held" and by["tables.update"]["agent_mode"] == "held"
    assert by["credentials.rotate"]["agent_mode"] == "no" and by["credentials.rotate"]["implemented"] is True
    r = prepared("source.test", {"source_id": "erp"})
    assert r["ok"] is False and r["error"]["code"] == "approval_required" and "secret" in r["error"]["message"]

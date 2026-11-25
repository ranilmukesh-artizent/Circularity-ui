"""P9-8.4 (story: enabler, 01 section 2 step 2's five person choices; G C5, D 1.4): accept, choose another field, accept
with a conversion, not needed, ask the owner. The choices are kept per source field and feed the memory of the vendor family;
a question to the system owner opens a My work item and holds `mapping.apply` until it is answered.

No source-sim and no model: two generic sources of one vendor family hold a stored sample (raw_record) and a system owner.
R21: agents never answer for a person (`mapping.answerOwner` is forbidden), a choice and an apply they prepare are held.
"""
# ruff: noqa: E501 - long lines in the SQL and the call bodies

import json

import pytest
from sqlalchemy import text

from di.connectors import connection, mapping, mapping_suggest
from di.core.db import SessionLocal, engine
from di.repositories import mapping_decisions
from di.services.agents import runtime
from di.services.agents.forbidden import HELD_FOR_PERSON, forbidden
from di.services.agents.pydantic_ai_loop import PydanticAILoop
from tests import starting
from tests.helpers import call, client, h

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")


@pytest.fixture(autouse=True)
def no_model():
    """The deterministic path (R16): with a live key the model would rerank first and `proposed_by` would read model."""
    runtime.set_loop(PydanticAILoop(lambda _s, _run, _role: None))
    yield
    runtime.set_loop(None)


A, B = "t84a", "t84b"  # two sources of the vendor family "oracle"
RES = "parts"
AGENT = "coordinator"  # seeded, autonomy act
SERIAL = "asset.serial_number"
REQUIRED = "asset.asset_id"


def _clean() -> None:
    with engine.begin() as c:
        for t in ("raw_record", "source_connection", "field_mapping", "mapping_decision"):
            c.execute(text(f"DELETE FROM {t} WHERE source_id = ANY(:i)"), {"i": [A, B]})  # noqa: S608 - fixed names
        c.execute(text("DELETE FROM work_item WHERE type LIKE 'mapping_owner:%'"))
        c.execute(text("DELETE FROM agent_proposal"))
        c.execute(text("DELETE FROM source_system WHERE id = ANY(:i)"), {"i": [A, B]})


def _source(sid: str, vendor: str, owner: str | None = "approver") -> None:
    with SessionLocal() as s:
        s.execute(
            text(
                "INSERT INTO source_system (id, vendor, type, status, interval_min, authority, owner, org_unit_id) "
                "VALUES (:i, :v, 'erp', 'live', 30, '{}', 'Integration Engineering', 'Customer A')"
            ),
            {"i": sid, "v": vendor},
        )
        connection.save_connection(
            s,
            sid,
            "test",
            base_url="http://fake.test/api",
            auth_kind="none",
            resources=[{"name": RES, "path": "/p", "id_field": "id"}],
        )
        connection.tag(s, sid, environment="test", system_owner=owner, registry_id="generic-rest", registry_version=1)
        for n, (serial, wt) in enumerate([("MTR-2041", "10"), ("MTR-2042", "22")]):
            s.execute(
                text("INSERT INTO raw_record (source_id, resource, ext_id, payload) VALUES (:s, :r, :e, CAST(:p AS jsonb))"),
                {"s": sid, "r": RES, "e": f"p{n}", "p": json.dumps({"SERNR": serial, "WT_LB": wt})},
            )
        s.commit()


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    _clean()
    _source(A, "Oracle Parts Hub")
    _source(B, "Oracle Spares")
    yield
    _clean()
    starting.reset()


def _decide(sid: str, src: str, decision: str, user: str = "developer", **kw: object) -> dict:
    return call("mapping.decide", {"source_id": sid, "src": src, "decision": decision, **kw}, user)


def _version(sid: str) -> int | None:
    with SessionLocal() as s:
        return mapping.active_version(s, sid)


def _suggest(sid: str) -> dict[str, dict]:
    r = call("mapping.suggest", {"source_id": sid, "resource": RES}, "developer")
    assert r["ok"], r
    return {x["field"]: x for x in r["output"]["rows"]}


# ---------------------------------------------------------------- memory
def test_mapping_choice_accept_records_memory():
    """P9-8.4: accept SERNR -> asset.serial_number on one source; a second source of the family gets proposed_by memory."""
    assert _suggest(B)["SERNR"]["proposed_by"] != "memory"
    r = _decide(A, "SERNR", "accepted", target=SERIAL)
    assert r["ok"] and r["output"]["decision"] == "accepted" and r["output"]["target"] == SERIAL, r
    with SessionLocal() as s:
        assert mapping_decisions.memory_for(s, "oracle") == {"SERNR": SERIAL}
        assert mapping_decisions.memory_for(s, "sap") == {}
    row = _suggest(B)["SERNR"]
    assert row["proposed_by"] == "memory" and row["target"] == SERIAL and row["decision"] is None, row
    assert _suggest(A)["SERNR"]["decision"]["decision"] == "accepted"


def test_mapping_choice_replace_is_negative_memory():
    """P9-8.4: replacing a proposal puts the corrected target in the memory and drops the refused one."""
    _decide(A, "SERNR", "accepted", target=SERIAL)
    r = _decide(B, "SERNR", "replaced", target="asset.location", proposed=SERIAL)
    assert r["ok"], r
    with SessionLocal() as s:
        assert mapping_decisions.memory_for(s, "oracle") == {"SERNR": "asset.location"}
    assert SERIAL not in {x["target"] for x in _suggest(B).values() if x["proposed_by"] == "memory"}
    assert _decide(B, "SERNR", "replaced")["error"]["code"] == "validation_error"  # `replaced` needs a target
    assert _decide(B, "SERNR", "replaced", target="widget.x")["error"]["code"] == "validation_error"


def test_mapping_choice_supersedes_the_older_choice_of_a_field():
    _decide(A, "SERNR", "accepted", target=SERIAL)
    _decide(A, "SERNR", "not_needed")
    with SessionLocal() as s:
        live = mapping_decisions.of_source(s, A)
        assert [d["decision"] for d in live] == ["not_needed"]
        assert mapping_decisions.memory_for(s, "oracle") == {}


# ---------------------------------------------------------------- conversion and required fields
def test_mapping_choice_conversion_shows_values():
    """P9-8.4: accepted_with_rule units:lb>kg on the samples 10 and 22 answers 4.54 and 9.98 at once."""
    r = _decide(A, "WT_LB", "accepted_with_rule", target="asset.stock_qty", rule="units:lb>kg", resource=RES)
    assert r["ok"], r
    out = r["output"]
    assert out["rule"] == "units:lb>kg" and out["samples"] == ["10", "22"] and out["values"] == [4.54, 9.98], out
    bad = _decide(A, "WT_LB", "accepted_with_rule", target="asset.stock_qty", rule="units:lb>parsec")
    assert bad["ok"] is False and bad["error"]["code"] == "validation_error", bad


def test_mapping_choice_not_needed_required_warns():
    """P9-8.4: marking a required canonical field not needed answers the blocking warning; apply refuses it."""
    r = _decide(A, "ID", "not_needed", target=REQUIRED)
    assert r["ok"] and r["output"]["blocking"] is True, r
    assert r["output"]["warning"] == f"Required field {REQUIRED} is marked not needed."
    ok = _decide(A, "SKU", "not_needed")
    assert ok["ok"] and "warning" not in ok["output"], ok
    ap = call("mapping.apply", {"source_id": A, "rows": [{"src": "SERNR", "target": SERIAL}]}, "developer")
    assert ap["ok"] is False and ap["error"] == {
        "code": "conflict",
        "message": f"Required field {REQUIRED} is marked not needed.",
    }, ap
    assert _version(A) is None


# ---------------------------------------------------------------- ask the owner
def test_mapping_ask_owner_opens_work_item():
    """P9-8.4: one My work item for the owner with three masked samples; apply waits until the owner answers; then v+1."""
    r = call(
        "mapping.askOwner",
        {"source_id": A, "src": "SERNR", "question": "Is this the asset serial or the lot?", "resource": RES},
        "developer",
    )
    assert r["ok"], r
    out = r["output"]
    assert out["owner"] == "approver" and out["samples"] == ["MTR-2041", "MTR-2042"], out
    with SessionLocal() as s:
        items = s.execute(text("SELECT * FROM work_item WHERE type = :t"), {"t": f"mapping_owner:{out['id']}"}).mappings().all()
        assert len(items) == 1 and items[0]["status"] == "open" and items[0]["owner_account"] == "approver", items
        assert "MTR-2041" in items[0]["cause"] and "serial or the lot" in items[0]["cause"]
    rows = [{"src": "SERNR", "target": SERIAL, "resource": RES}]
    wait = call("mapping.apply", {"source_id": A, "rows": rows}, "developer")
    assert wait["ok"] is False and wait["error"] == {
        "code": "conflict",
        "message": "Waiting for the system owner on 1 field.",
    }, wait
    assert call("mapping.suggest", {"source_id": A, "resource": RES}, "developer")["output"]["waiting"] == 1
    ans = call("mapping.answerOwner", {"decision_id": out["id"], "decision": "accepted", "target": SERIAL}, "approver")
    assert ans["ok"] and ans["output"]["target"] == SERIAL, ans
    with SessionLocal() as s:
        assert s.execute(text("SELECT status FROM work_item WHERE id = :i"), {"i": out["item_id"]}).scalar() == "done"
        assert mapping_decisions.memory_for(s, "oracle") == {"SERNR": SERIAL}
    assert _version(A) is None
    done = call("mapping.apply", {"source_id": A, "rows": rows, "note": "after the owner"}, "developer")
    assert done["ok"], done
    assert done["output"]["version"] == 1 and _version(A) == 1  # a source made here has no default version before it
    with SessionLocal() as s:
        assert [(r.src, r.model, r.field) for r in mapping.active_rows(s, A)] == [("SERNR", "asset", "serial_number")]


def test_mapping_apply_merges_with_the_saved_rows_and_uses_the_save_path():
    first = call("mapping.apply", {"source_id": A, "rows": [{"src": "SERNR", "target": SERIAL}]}, "developer")
    assert first["ok"], first
    second = call(
        "mapping.apply",
        {"source_id": A, "rows": [{"src": "WT_LB", "target": "asset.stock_qty", "rule": "units:lb>kg"}]},
        "developer",
    )
    assert (
        second["ok"] and second["output"]["version"] == first["output"]["version"] + 1 and second["output"]["rows"] == 2
    ), second
    again = call(
        "mapping.apply",
        {"source_id": A, "rows": [{"src": "WT_LB", "target": "asset.stock_qty", "rule": "units:lb>kg"}]},
        "developer",
    )
    assert again["ok"] is False and again["error"]["message"] == "No changes to save."
    empty = call("mapping.apply", {"source_id": A, "rows": []}, "developer")
    assert empty["ok"] is False and empty["error"]["code"] == "validation_error"
    src = client.get(f"/api/screens/integration/sources/{A}", headers=h("developer")).json()["source"]
    assert "Field mapping saved" in src["audit"][0]["change"]  # the same audit entry mapping.save writes


def test_mapping_ask_owner_without_owner_or_question_refused():
    _source("t84c", "Oracle Nobody", owner=None)
    try:
        r = call("mapping.askOwner", {"source_id": "t84c", "src": "SERNR", "question": "Which field is this?"}, "developer")
        assert r["ok"] is False and r["error"]["code"] == "validation_error" and "system owner" in r["error"]["message"], r
    finally:
        with engine.begin() as c:
            for t in ("raw_record", "source_connection"):
                c.execute(text(f"DELETE FROM {t} WHERE source_id = 't84c'"))  # noqa: S608 - fixed names
            c.execute(text("DELETE FROM source_system WHERE id = 't84c'"))
    short = call("mapping.askOwner", {"source_id": A, "src": "SERNR", "question": "?"}, "developer")
    assert short["ok"] is False, short


def test_mapping_choice_closes_the_question_when_a_person_decides_directly():
    q = call("mapping.askOwner", {"source_id": A, "src": "SERNR", "question": "Serial or lot number?"}, "developer")["output"]
    assert _decide(A, "SERNR", "accepted", target=SERIAL)["ok"]
    with SessionLocal() as s:
        assert s.execute(text("SELECT status FROM work_item WHERE id = :i"), {"i": q["item_id"]}).scalar() == "done"
        assert mapping_decisions.open_questions(s, A) == []


# ---------------------------------------------------------------- agents and access
def test_mapping_decide_agent_held():
    """P9-8.4: an agent's choice and apply are held proposals; nothing is recorded or saved."""
    hdr = h("developer") | {"X-Circularity-Preparer": AGENT}
    r = client.post(
        "/api/actions/mapping.decide",
        json={"source_id": A, "src": "SERNR", "decision": "accepted", "target": SERIAL},
        headers=hdr,
    ).json()
    assert r["ok"] is True and set(r["output"]) == {"held", "reasons"}, r
    r = client.post(
        "/api/actions/mapping.apply", json={"source_id": A, "rows": [{"src": "SERNR", "target": SERIAL}]}, headers=hdr
    ).json()
    assert r["ok"] is True and set(r["output"]) == {"held", "reasons"}, r
    with SessionLocal() as s:
        assert mapping_decisions.of_source(s, A) == []
        assert mapping.active_version(s, A) is None
        assert s.execute(text("SELECT count(*) FROM agent_proposal")).scalar() == 2
    bad = client.post(
        "/api/actions/mapping.decide",
        json={"source_id": A, "src": "SERNR", "decision": "accepted", "target": "widget.x"},
        headers=hdr,
    ).json()
    assert bad["ok"] is False and bad["error"]["code"] == "validation_error", bad  # invalid: refused, not held


def test_mapping_agent_may_ask_but_never_answer():
    hdr = h("developer") | {"X-Circularity-Preparer": AGENT}
    asked = client.post(
        "/api/actions/mapping.askOwner", json={"source_id": A, "src": "SERNR", "question": "Serial or lot number?"}, headers=hdr
    ).json()
    assert asked["ok"] is True and "id" in asked["output"], asked
    did = asked["output"]["id"]
    hdr = h("approver") | {"X-Circularity-Preparer": AGENT}
    r = client.post(
        "/api/actions/mapping.answerOwner", json={"decision_id": did, "decision": "accepted", "target": SERIAL}, headers=hdr
    ).json()
    assert r["ok"] is False and r["error"]["code"] == "approval_required", r
    with SessionLocal() as s:
        assert [d["decision"] for d in mapping_decisions.of_source(s, A)] == ["asked_owner"]
    assert forbidden("mapping.answerOwner") and not forbidden("mapping.askOwner")
    assert {"mapping.decide", "mapping.apply", "mapping.save"} <= set(HELD_FOR_PERSON)


def test_mapping_answer_owner_only_owner():
    """P9-8.4: another Planner answering is out_of_scope; the owner and an integration manager may."""
    q = call("mapping.askOwner", {"source_id": A, "src": "SERNR", "question": "Serial or lot number?"}, "developer")["output"]
    body = {"decision_id": q["id"], "decision": "accepted", "target": SERIAL}
    r = call("mapping.answerOwner", body, "planner.a")
    assert r["ok"] is False and r["error"]["code"] == "out_of_scope", r
    with SessionLocal() as s:
        assert [d["decision"] for d in mapping_decisions.open_questions(s, A)] == ["asked_owner"]
    assert (
        call("mapping.answerOwner", {"decision_id": q["id"], "decision": "accepted"}, "approver")["error"]["code"]
        == "validation_error"
    )
    assert call("mapping.answerOwner", body, "approver")["ok"]
    again = call("mapping.answerOwner", body, "approver")
    assert again["ok"] is False and again["error"]["code"] == "conflict", again
    assert (
        call("mapping.answerOwner", {"decision_id": 0, "decision": "accepted", "target": SERIAL}, "approver")["error"]["code"]
        == "not_found"
    )


def test_mapping_decide_wrong_role_and_unknown_source():
    r = _decide(A, "SERNR", "accepted", user="planner.a", target=SERIAL)
    assert r["ok"] is False and r["error"]["code"] in ("out_of_scope", "forbidden"), r
    assert _decide("nope", "SERNR", "accepted", target=SERIAL)["error"]["code"] == "not_found"
    assert _decide(A, "SERNR", "asked_owner")["error"]["code"] == "validation_error"


def test_mapping_suggest_still_masks_and_carries_no_decision_without_one():
    rows = _suggest(A)
    assert {json.dumps(r["decision"]) for r in rows.values()} == {"null"}
    assert mapping_suggest.MASK not in json.dumps(rows["SERNR"]["samples"])

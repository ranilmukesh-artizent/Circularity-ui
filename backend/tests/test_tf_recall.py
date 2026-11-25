"""Plan 9, P9-3.7 (story TF-04): the safety recall check GR-12 and the quarantine release.

`fleet_evidence.recall_check` (pure) reads the active recall notices whose serial range holds the tool's serial. A `repair`
recall blocks `release`, `redeploy` and `resell` until Quality releases the tool after the fix (`recall.release`); `refurb`
(the repair is done there), `harvest` and `exit` stay. A `replace` or `refund` recall leaves only `exit` and `harvest`, and
harvest never certifies a part the recall names; such a tool is never released to the fleet. The pack lists the gate
`G-TOOL-REC` (params guardrail GR-12, locked: a customer overlay cannot skip it) and the exception type `recall_quarantine`
(Quality). The sample world has no recall, so its numbers do not move.

Maker-checker does not apply to `recall.release` (it releases a block; nobody "made" it), so R21's maker test is replaced by
the two tests of TF-04 (a replace recall cannot be released; no quarantine, no release) and the three security tests here:
an agent is refused, a Planner is refused, and the tenant boundary holds. No model step: the check reads notices.

It starts and ends with the demo reset.
"""

import pytest
from sqlalchemy import text

from di.core import policy
from di.core.db import SessionLocal, engine
from di.services.actions.registry import ACTIONS
from di.services.agents import catalog
from di.services.agents.forbidden import FORBIDDEN_ACTIONS, forbidden
from di.services.canonical import store as canonical
from di.services.cases import store
from di.services.modeler import gates
from di.services.modeler.overlay import OverlayError, Shortcut, apply_overlay
from di.services.modeler.pack import load_pack
from di.services.modeler.valuers import fleet_evidence
from tests import starting
from tests.helpers import call, client, h, tool_case_facts

ORDER = {"kind": "lease", "id": "L-1", "renew": True, "who": "Acme Rentals", "site": "Houston", "need": 9, "rate": 900,
         "term": 24, "what": "Fleet contract L-1 renews", "when": "renewal confirmed"}  # fmt: skip
REPAIR = {"recall_id": "RC-2026-017", "tool_class": "BRK", "serial_from": "BRK-51000", "serial_to": "BRK-51999",
          "remedy": "repair", "affected_parts": ["Impact mechanism"], "status": "active"}  # fmt: skip
REPLACE = {"recall_id": "RC-2026-014", "tool_class": "CRH", "serial_from": "CRH-44000", "serial_to": "CRH-44999",
           "remedy": "replace", "affected_parts": ["Brushless motor"], "status": "active"}  # fmt: skip
CLOSED = {"recall_id": "RC-2026-009", "tool_class": "DCD", "serial_from": "DCD-30000", "serial_to": "DCD-30999",
          "remedy": "refund", "affected_parts": ["Drill stand"], "status": "closed"}  # fmt: skip
REPAIR_WHY = "Safety recall RC-2026-017 (repair): quarantined until Quality releases it"


# ------------------------------------------------------------------ the pure check
def test_tf_04_check_no_recall_passes():
    r, paths, parts = fleet_evidence.recall_check("BRK-51007", "BRK", [], None)
    assert r.passed and r.gate_id == "G-TOOL-REC" and not paths and not parts


def test_tf_04_check_serial_outside_the_range_or_a_closed_notice_is_ignored():
    for notice, serial, cls in (
        (REPAIR, "BRK-52000", "BRK"),
        (REPAIR, "BRK-50999", "BRK"),
        (REPAIR, "BRK-51007", "CMH"),
        (CLOSED, "DCD-30001", "DCD"),
    ):
        r, paths, parts = fleet_evidence.recall_check(serial, cls, [notice], None)
        assert r.passed and not paths and not parts, (notice["recall_id"], serial)


def test_tf_04_check_repair_blocks_three_paths_and_the_part_until_released():
    r, paths, parts = fleet_evidence.recall_check("BRK-51007", "BRK", [REPAIR, CLOSED], None)
    assert not r.passed and r.reason == REPAIR_WHY
    assert r.effect.kind == "block" and not r.effect.hold and r.effect.step == "Quarantine"
    assert set(paths) == {"release", "redeploy", "resell"} == set(r.effect.routes)
    assert parts == frozenset({"Impact mechanism"})
    released = {"recall_id": "RC-2026-017", "by": "approver", "at": "2026-11-25T10:00:00+00:00", "note": "Fixed at the depot"}
    r, paths, parts = fleet_evidence.recall_check("BRK-51007", "BRK", [REPAIR], released)
    assert r.passed and not paths and not parts and "approver" in r.reason
    other = released | {"recall_id": "RC-2026-099"}  # a release of another notice releases nothing here
    assert not fleet_evidence.recall_check("BRK-51007", "BRK", [REPAIR], other)[0].passed


def test_tf_04_check_replace_leaves_exit_and_harvest_and_is_never_released():
    r, paths, parts = fleet_evidence.recall_check("CRH-44120", "CRH", [REPLACE], None)
    assert not r.passed and set(paths) == {"release", "refurb", "redeploy", "resell"} and parts == frozenset({"Brushless motor"})
    released = {"recall_id": "RC-2026-014", "by": "approver", "at": "2026-11-25T10:00:00+00:00", "note": "Trying"}
    again, paths2, _ = fleet_evidence.recall_check("CRH-44120", "CRH", [REPLACE], released)
    assert not again.passed and set(paths2) == set(paths)  # a release of a replace recall changes nothing


def test_tf_04_pack_lists_gr_12_locked_and_the_exception_type():
    pack = load_pack("tool_fleet")
    g = next(g for g in gates.pack_gates(pack) if g.id == "G-TOOL-REC")
    assert g.locked and g.params["guardrail"] == "GR-12" and g.stage == "match"
    kind = next(t for t in pack.runtime.exception_types if t.id == "recall_quarantine")
    assert kind.owner_role == "Quality" and pack.roles["Quality"] == "Approver"


def test_tf_04_skip_recall_diversion_refused():
    """A customer's overlay op "new tool under 3 months: skip the recall check" skips the match stage: refused, and the
    refusal names the recall gate (the pack's GR-12)."""
    op = Shortcut(id="op-1", op="shortcut", stage="receive", when=[{"fact": "age", "op": "lte", "value": 3}], to="condition")
    with pytest.raises(OverlayError) as e:
        apply_overlay(load_pack("tool_fleet"), [op])
    assert e.value.code == "skips_compliance" and e.value.guardrail == "G-TOOL-REC"
    assert "Safety recall check" in str(e.value)
    pack = load_pack("tool_fleet")
    assert next(g for g in gates.pack_gates(pack) if g.id == e.value.guardrail).params["guardrail"] == "GR-12"


def test_tf_04_the_sample_world_has_no_recall():
    ev = fleet_evidence.sample_evidence({"id": "RT-1", "serial": "BRK-51007"})
    assert ev["recall_check"].result == "pass" and not ev["recall_check"].value["recalls"]


def test_tf_04_recall_release_is_declared_forbidden_to_agents():
    a = ACTIONS["recall.release"]
    assert a.risk == "commit" and a.perm == "releaseQuarantine" and a.scope == "case"
    assert forbidden("recall.release") and "recall.release" in FORBIDDEN_ACTIONS
    assert catalog.agent_allowed(a) is False and catalog.agent_mode(a) == "no"
    assert policy.EXTRA_PERMS["releaseQuarantine"] == ("Admin", "Approver")


# ------------------------------------------------------------------ cases opened from data
def _clean() -> None:
    """The notices, lines and contracts these tests write stay in the canonical store through a reset: drop them."""
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM provenance WHERE model IN ('recall', 'contract_line', 'contract')"))
        conn.execute(text("DELETE FROM canonical WHERE model IN ('recall', 'contract_line', 'contract')"))


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    _clean()
    yield
    starting.reset()
    _clean()


def _notice(n: dict) -> None:
    with SessionLocal() as s:
        canonical.apply(s, "recall", [canonical.Fact("recall", n["recall_id"], k, v, resource="notices") for k, v in n.items()])
        s.commit()


def _open(serial: str, grade: str = "B", **dem) -> str:
    cls = serial.split("-")[0]
    facts = {"cls": cls, "grade": grade, "ft": "Repair center", "site": "Houston", "rul": 62,
             "dem": {"lease": [ORDER], "wo": {}} | dem}  # fmt: skip
    body = {"org_unit_id": "Customer A", "template_key": "tool_fleet", "asset_key": serial, "reason": "manual",
            "facts": tool_case_facts(serial, facts)}  # fmt: skip
    r = call("case.open", body, "planner-a")
    assert r["ok"], r
    return r["output"]["case_id"]


def _case(cid: str) -> dict:
    with SessionLocal() as s:
        c = store.get(s, cid)
    assert c is not None
    return c


def _open_routes(c: dict) -> set[str]:
    return {r["id"] for r in c["routes"] if not r["excluded"]}


def _items(cid: str) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT type, owner_role, action, status FROM work_item "
                "WHERE case_id = :c AND type = 'recall_quarantine' ORDER BY id"
            ),
            {"c": cid},
        )
        return [dict(r._mapping) for r in rows]


def test_tf_04_replace_recall_leaves_exit_and_safe_harvest():
    _notice(REPLACE)
    wo = {"Brushless motor": [{"id": "WO-91", "who": "Houston depot", "backorder": False}],
          "Electronics module": [{"id": "WO-92", "who": "Houston depot", "backorder": False}]}  # fmt: skip
    c = _case(_open("CRH-44120", wo=wo))
    assert _open_routes(c) == {"exit", "harvest"}, [(r["id"], r["failReason"]) for r in c["routes"]]
    harvest = next(r for r in c["routes"] if r["id"] == "harvest")
    labels = [x["label"] for x in harvest.get("terms") or []]
    assert any("Electronics module" in x for x in labels) and not any("Brushless motor" in x for x in labels), labels
    blocked = next(r for r in c["routes"] if r["id"] == "refurb")
    assert "Safety recall RC-2026-014 (replace)" in blocked["failReason"]
    assert c["requiredSteps"][0]["step"] == "Quarantine" and c["requiredSteps"][0]["owner"] == "Quality"
    (item,) = [i for i in _items(c["id"]) if i["status"] == "open"]
    assert item["owner_role"] == "Approver"  # Quality is an Approver of the programme (the pack's roles table)


def test_tf_04_repair_recall_blocks_until_released():
    _notice(REPAIR)
    cid = _open("BRK-51007", "A")
    c = _case(cid)
    assert {"release", "redeploy", "resell"}.isdisjoint(_open_routes(c))
    assert REPAIR_WHY in next(r for r in c["routes"] if r["id"] == "release")["failReason"]
    assert "refurb" in _open_routes(c) or "harvest" in _open_routes(c) or "exit" in _open_routes(c)
    assert [i["status"] for i in _items(cid)] == ["open"]
    r = call("recall.release", {"case_id": cid, "note": "Impact mechanism replaced at the depot"}, "approver")
    assert r["ok"], r
    c = _case(cid)
    assert "release" in _open_routes(c), [(x["id"], x["failReason"]) for x in c["routes"]]
    assert c["recallRelease"]["by"] == "approver" and c["recallRelease"]["note"] == "Impact mechanism replaced at the depot"
    assert c["recallRelease"]["recall_id"] == "RC-2026-017"
    assert [i["status"] for i in _items(cid)] == ["done"]
    assert not c.get("requiredSteps")


def test_tf_04_replace_cannot_be_released():
    _notice(REPLACE)
    cid = _open("CRH-44120")
    r = call("recall.release", {"case_id": cid, "note": "Release it anyway"}, "approver")
    assert r["ok"] is False and r["error"]["code"] == "conflict"
    assert r["error"]["message"] == "A replace or refund recall is never released to the fleet"
    assert "recallRelease" not in _case(cid)


def test_tf_04_release_without_a_quarantine_is_a_conflict():
    cid = _open("CMH-48213")
    r = call("recall.release", {"case_id": cid, "note": "Nothing to release"}, "approver")
    assert r["ok"] is False and r["error"]["code"] == "conflict"


def test_tf_04_screen_shows_the_quarantine():
    _notice(REPAIR)
    cid = _open("BRK-51007", "A")
    v = client.get(f"/api/screens/toolfleet/{cid}", headers=h("approver")).json()
    q = v["quarantine"]
    assert q["recall_id"] == "RC-2026-017" and q["remedy"] == "repair" and q["released"] is None
    assert set(q["blocked"]) == {"release", "redeploy", "resell"} and q["affected_parts"] == ["Impact mechanism"]
    g = next(x for x in v["gates"] if x["id"] == "G-TOOL-REC")
    assert g["passed"] is False and g["guardrail"] == "GR-12" and g["reason"] == REPAIR_WHY
    assert call("recall.release", {"case_id": cid, "note": "Fixed at the depot"}, "approver")["ok"]
    v = client.get(f"/api/screens/toolfleet/{cid}", headers=h("approver")).json()
    assert v["quarantine"]["released"]["by"] == "approver" and v["quarantine"]["blocked"] == []


def test_tf_04_the_case_without_a_recall_has_no_quarantine():
    cid = _open("CMH-48213")
    v = client.get(f"/api/screens/toolfleet/{cid}", headers=h("admin")).json()
    assert v["quarantine"] is None
    assert any(g["id"] == "G-TOOL-REC" and g["passed"] for g in v["gates"])


# ------------------------------------------------------------------ security (R21)
def test_quarantine_agent_cannot_release():
    _notice(REPAIR)
    cid = _open("BRK-51007", "A")
    r = client.post("/api/actions/recall.release", json={"case_id": cid, "note": "An agent decides it is fine"},
                    headers=h("approver") | {"X-Circularity-Preparer": "coordinator"}).json()  # fmt: skip
    assert r["ok"] is False and r["error"]["code"] == "approval_required", r
    assert "recallRelease" not in _case(cid)


def test_quarantine_planner_cannot_release():
    _notice(REPAIR)
    cid = _open("BRK-51007", "A")
    r = call("recall.release", {"case_id": cid, "note": "A planner may not release"}, "planner-a")
    assert r["ok"] is False and r["error"]["code"] == "out_of_scope"
    assert "recallRelease" not in _case(cid)


def test_quarantine_tenant_boundary(monkeypatch):
    """An Approver without the case's tenant in scope is refused at the boundary (granted the right here, planner-b stands for
    an account whose tenant is not the case's)."""
    _notice(REPAIR)
    cid = _open("BRK-51007", "A")
    monkeypatch.setitem(policy.EXTRA_PERMS, "releaseQuarantine", ("Admin", "Approver", "Planner"))
    r = call("recall.release", {"case_id": cid, "note": "Another customer's tool"}, "planner-b")
    assert r["ok"] is False and r["error"]["code"] == "tenant_boundary", r
    assert "recallRelease" not in _case(cid)

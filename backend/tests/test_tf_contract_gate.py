"""Plan 9, P9-3.6 (story TF-02): the contract right gate GR-07. A tool without an active contract line has no route.

`fleet_evidence.contract_check` (pure) says why a line does not give the right to dispose of the tool: no line, a status
other than active (a returned line at the end of its term or for a swap is fine), a theft claim or a damage charge still
open, a line owned by another org. The pack gates every tool-fleet case with it (catalogue gate G-CON-2, the pack's gate ref
of GR-07), before any business rule (R20): all six routes are excluded with the reason, the case is held and one exception
item `no_active_contract` is open for the Fleet desk (a Planner). A later sync that clears the line releases it. The
sample world (`tool_fleet.sample_live_cases()`) is decided with a complete sample line, so the PO goldens keep their
numbers. No model step: the check reads the line, it never writes language.

It starts and ends with the demo reset.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from di import worker
from di.core import golden
from di.core.db import SessionLocal, engine
from di.services.canonical import store as canonical
from di.services.cases import intake
from di.services.cases.decide import decide_case
from di.services.modeler import gates
from di.services.modeler.compile import FlowVersion
from di.services.modeler.evidence import Evidence
from di.services.modeler.pack import load_pack
from di.services.modeler.valuers import fleet_evidence, tool_fleet
from tests import starting
from tests.helpers import LINE_OWNER, call, client, h, tool_case_facts

ORG = "tool-fleet-a"
OWNER = LINE_OWNER
ACTIVE = {"serial": "CMH-48213", "status": "active", "returnReason": None, "theftClaimOpen": False, "claimRef": None,
          "damageChargeOpen": False, "chargeRef": None, "ownerOrg": OWNER}  # fmt: skip


def _line(**over):
    return ACTIVE | over


# ------------------------------------------------------------------ the pure check
def test_tf_02_check_no_line_blocks():
    r = fleet_evidence.contract_check(None, OWNER, serial="CMH-99999")
    assert not r.passed and r.effect.kind == "block" and r.reason == "No active contract for serial CMH-99999"
    assert r.gate_id == "G-CON-2"


def test_tf_02_check_active_passes_and_a_returned_end_of_term_or_swap_passes():
    assert fleet_evidence.contract_check(_line(), OWNER).passed
    for why in ("end_of_term", "swap"):
        assert fleet_evidence.contract_check(_line(status="returned", returnReason=why), OWNER).passed, why
    r = fleet_evidence.contract_check(_line(status="returned", returnReason="repair"), OWNER)
    assert not r.passed and "returned" in r.reason and "FL" not in r.reason
    assert not fleet_evidence.contract_check(_line(status="terminated"), OWNER).passed


def test_tf_02_check_names_the_term():
    theft = _line(status="returned", returnReason="theft_recovered", theftClaimOpen=True, claimRef="CLM-7781")
    assert fleet_evidence.contract_check(theft, OWNER).reason == "Theft recovered: claim CLM-7781 is open"
    dmg = _line(damageChargeOpen=True, chargeRef="CHG-4412")
    assert fleet_evidence.contract_check(dmg, OWNER).reason == "Damage charge CHG-4412 is open"
    other = _line(ownerOrg="Fleet Europe")
    assert fleet_evidence.contract_check(other, OWNER).reason == "Owned by Fleet Europe, not by this programme"
    assert fleet_evidence.contract_check(_line(ownerOrg=None), OWNER).passed  # an owner not on file is not a reason


def test_tf_02_sample_evidence_is_an_active_line():
    ev = fleet_evidence.sample_evidence({"id": "RT-1", "serial": "CMH-48213"})
    e = ev["contract_line"]
    assert isinstance(e, Evidence) and e.result == "pass" and e.value["status"] == "active"
    assert fleet_evidence.contract_check(e.value, OWNER).passed


def test_tf_02_the_pack_gates_every_route_with_gr_07():
    pack = load_pack("tool_fleet")
    assert pack.owner == OWNER
    assert pack.roles["Fleet desk"] == "Planner" and pack.roles["Quality"] == "Approver" and pack.roles["Finance"] == "Finance"
    g = next(g for g in gates.pack_gates(pack) if g.id == "G-CON-2")
    assert g.locked and g.effect.kind == "block" and g.effect.hold_until_evidence and g.params["guardrail"] == "GR-07"
    assert len(gates.gate_routes(g, pack)) == len(pack.routes) == 6
    kind = next(t for t in pack.runtime.exception_types if t.id == "no_active_contract")
    assert kind.owner_role == "Fleet desk" and kind.action == "Check the contract line in the fleet contract system"


# ------------------------------------------------------------------ the sample world
def test_tf_02_sample_world_unchanged():
    """Deciding every case of the sample world through `decide_case` (the pack's gates run first; the Modeler's queue does)
    gives the golden best path and net of equip_decisions.json."""
    want = golden.load("po/equip_decisions")["decisions"]
    r = client.get("/api/screens/modeler", params={"template": "tool_fleet", "org": "Customer A"}, headers=h("planner-a"))
    assert r.status_code == 200, r.text
    rows = {q["id"]: q for q in r.json()["queue"]}
    for w in want:
        assert rows[w["id"]]["best"] == w["best"]["k"], w["id"]
        assert rows[w["id"]]["net"] == pytest.approx(w["best"]["net"], abs=0.005), w["id"]


# ------------------------------------------------------------------ cases opened from data
def _clean_lines() -> None:
    """The lines and contracts these tests write stay in the canonical store through a reset: drop them."""
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM provenance WHERE model IN ('contract_line', 'contract')"))
        conn.execute(text("DELETE FROM canonical WHERE model IN ('contract_line', 'contract')"))


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    _clean_lines()
    assert call("org.create", {"id": ORG, "parent_id": "workspace", "kind": "company", "name": "Tool fleet A"}, "admin")["ok"]
    yield
    starting.reset()
    _clean_lines()


def _open(serial: str, reason: str = "contract_end", org: str = ORG, **facts) -> dict:
    with SessionLocal() as s:
        given = {"tool_class": serial.split("-")[0], "site": "Houston", "grade": "B", "rul": 62} | facts
        c = intake.open_case(
            s, {"org_unit_id": org, "template_key": "tool_fleet", "asset_key": serial, "reason": reason, "facts": given}, "system"
        )
        s.commit()
    return c


def _gated(c: dict, term: str) -> set[str]:
    """The case has no route (every route excluded, no recommendation, held); the routes the gate itself failed with `term`."""
    assert c["recommendation"] is None and c["stage"] == "none" and all(r["excluded"] for r in c["routes"])
    return {r["id"] for r in c["routes"] if term in (r["failReason"] or "")}


def _items(case_id: str) -> list[dict]:
    with engine.connect() as c:
        rows = c.execute(
            text(
                "SELECT type, owner_role, cause, action, status FROM work_item "
                "WHERE case_id = :c AND type = 'no_active_contract' ORDER BY id"
            ),
            {"c": case_id},
        )
        return [dict(r._mapping) for r in rows]


def _line_facts(serial: str, **over):
    base = {"line_id": f"FL-{serial}", "contract_id": "FC-TEST", "serial": serial, "status": "active", "tool_class": serial[:3]}
    return [canonical.Fact("contract_line", serial, k, v, resource="lines") for k, v in (base | over).items()]


def _write(serial: str, **over) -> None:
    with SessionLocal() as s:
        canonical.apply(s, "fleet", _line_facts(serial, **over))
        canonical.apply(s, "fleet", [canonical.Fact("contract", "FC-TEST", "owner_org", OWNER, resource="contracts")])
        s.commit()


def test_tf_02_no_contract_blocks_every_route():
    tool_case_facts("CMH-48213")
    ctl = _open("CMH-48213")
    eligible = {r["id"] for r in ctl["routes"] if not r["excluded"]}  # what an active line leaves open
    assert eligible, (ctl["id"], ctl.get("gateHold"), [(r["id"], r["failReason"]) for r in ctl["routes"]])
    c = _open("CMH-99999")
    assert (
        len(c["routes"]) == 6 and _gated(c, "No active contract for serial CMH-99999") == eligible
    )  # the rest the valuer left out
    assert c["gateHold"]["gates"] == ["G-CON-2"]
    items = [i for i in _items(c["id"]) if i["status"] == "open"]
    assert len(items) == 1 and items[0]["type"] == "no_active_contract" and items[0]["owner_role"] == "Planner"
    assert items[0]["action"] == "Check the contract line in the fleet contract system"
    assert "No active contract for serial CMH-99999" in items[0]["cause"]


def test_tf_02_theft_recovered_blocks():
    _write("BRK-51007", status="returned", return_reason="theft_recovered", theft_claim_open=True, claim_ref="CLM-7781")
    c = _open("BRK-51007", reason="service_order")
    assert _gated(c, "Theft recovered: claim CLM-7781 is open")
    assert any(
        g["id"] == "G-CON-2" and not g["passed"] and g["reason"] == "Theft recovered: claim CLM-7781 is open" for g in c["gates"]
    )


def test_tf_02_damage_charge_blocks():
    _write("CRH-44120", damage_charge_open=True, charge_ref="CHG-4412")
    c = _open("CRH-44120")
    assert _gated(c, "Damage charge CHG-4412 is open")


def test_tf_02_other_owner_blocks():
    with SessionLocal() as s:
        canonical.apply(s, "fleet", _line_facts("AGR-20991", contract_id="FC-EU"))
        canonical.apply(s, "fleet", [canonical.Fact("contract", "FC-EU", "owner_org", "Fleet Europe", resource="contracts")])
        s.commit()
    c = _open("AGR-20991")
    assert _gated(c, "Owned by Fleet Europe, not by this programme")


def test_tf_02_active_line_passes():
    tool_case_facts("CMH-48213")
    c = _open("CMH-48213")
    assert c["recommendation"] is not None and c.get("gateHold") is None, (c["id"], c.get("gates"), c["routes"][3]["failReason"])
    assert any(g["id"] == "G-CON-2" and g["passed"] for g in c["gates"])
    assert any(not r["excluded"] for r in c["routes"])
    assert [i for i in _items(c["id"]) if i["status"] == "open"] == []


def test_tf_02_line_cleared_reevaluates():
    _write("CMH-48213", damage_charge_open=True, charge_ref="CHG-4412")
    c = _open("CMH-48213")
    assert c["recommendation"] is None and len([i for i in _items(c["id"]) if i["status"] == "open"]) == 1
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM job WHERE kind = 'case.gateRecheck'"))
    with SessionLocal() as s:  # the next sync: the charge is closed
        canonical.apply(s, "fleet", _line_facts("CMH-48213", damage_charge_open=False, charge_ref=None))
        s.commit()
    with engine.connect() as conn:
        jobs = list(conn.execute(text("SELECT payload FROM job WHERE kind = 'case.gateRecheck' AND status = 'queued'")).scalars())
    assert jobs == [{"asset_key": "CMH-48213"}]
    worker.HANDLERS["case.gateRecheck"](jobs[0])
    with SessionLocal() as s:
        from di.services.cases import store

        now = store.get(s, c["id"])
    assert now is not None and now.get("gateHold") is None and now["recommendation"] is not None
    assert now["stage"] == "awaiting_approval"
    assert [i["status"] for i in _items(c["id"])] == ["done"]


def test_tf_02_planner_sees_the_exception_in_my_work():
    c = _open("CMH-99999", org="Customer A")
    r = client.get("/api/screens/mywork", headers=h("planner.a"))
    assert r.status_code == 200, r.text
    row = next(
        i for i in r.json()["items"] if i["case_id"] == c["id"] and i["kind"] == "exception" and "contract" in i["action"].lower()
    )
    assert row["action"] == "Check the contract line in the fleet contract system"


def test_tf_02_screen_lists_the_gates():
    _write("BRK-51007", status="returned", return_reason="theft_recovered", theft_claim_open=True, claim_ref="CLM-7781")
    c = _open("BRK-51007", reason="service_order")
    r = client.get(f"/api/screens/toolfleet/{c['id']}", headers=h("admin"))
    assert r.status_code == 200, r.text
    g = next(x for x in r.json()["gates"] if x["id"] == "G-CON-2")
    assert g["passed"] is False and g["reason"] == "Theft recovered: claim CLM-7781 is open" and g["guardrail"] == "GR-07"
    assert g["name"] and g["owner"]


def test_tf_02_sample_clock_is_not_read():
    """The sample evidence is complete at any time the case is decided at."""
    pack = load_pack("tool_fleet")
    case = tool_fleet.sample_queue()[0]
    d = decide_case(case, pack, FlowVersion(None, 0, ()), datetime(2026, 1, 2, tzinfo=UTC), queue=tool_fleet.sample_live_cases())
    assert d.recommendation is not None and not [g for g in d.gates if not g.passed]

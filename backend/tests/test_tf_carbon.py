"""Plan 9, P9-3.14 (story TF-13): CO2e per route and the recycling certificate.

The figure is computed (`modeler/valuers/tool_carbon.py`, B 5.7 formulas, the pack's versioned factor table
`tf-co2-2026.1` with its source), never by a language model: no model step here, so no AgentLoop and no model tests. It is
information only (never enters `net`). The recycler's certificate is a compliance text, pending review by Kinective's Legal
team. The industrial demo's figures do not move (test_po_golden, test_screens_case).
"""

import pytest

from di.core.db import SessionLocal
from di.services.modeler.pack import load_pack
from di.services.modeler.valuers import tool_carbon
from tests import starting
from tests.helpers import call, client, h

ORG = "tool-fleet-co2"
CMH = {
    "version": "tf-co2-2026.1",
    "source": "Sample factors (synthetic)",
    "year": 2026,
    "classes": {
        "CMH": {
            "embodied_new_kg": 85, "mass_kg": 12, "prep_kg": 1.5, "refurb_kg": 6, "teardown_kg": 2,
            "recycle_credit_kg_per_kg": 1.8, "treat_kg": 0.4, "road_kg_per_tkm": 0.1, "lane_km": 400,
        }
    },
}  # fmt: skip
RENEWAL = {"kind": "lease", "id": "FC-1", "other_site": False}


def test_tf_13_co2_per_route():
    rel = tool_carbon.co2_avoided("release", "CMH", RENEWAL, 0, CMH)
    assert rel.kg == 83.5 and rel.version == "tf-co2-2026.1" and rel.source == "Sample factors (synthetic)"
    assert rel.formula == "85 x 1 - 1.5 - 0"
    ext = tool_carbon.co2_avoided("exit", "CMH", {"kind": "exit", "id": "Q1"}, 0, CMH)
    assert ext.kg == 21.2 and ext.formula == "12 x 1.8 - 0.4"


def test_tf_13_formulas_of_the_other_paths():
    f = tool_carbon.co2_avoided
    forecast = {"kind": "market", "id": "x", "other_site": True}
    assert f("resell", "CMH", forecast, 0, CMH).kg == round(85 * 0.5 - 1.5 - 0.48, 1)  # d 0.5, E_log 12/1000 x 400 x 0.1
    assert f("resell", "CMH", {"kind": "bid", "id": "b", "other_site": True}, 0, CMH).kg == round(85 - 1.5 - 0.48, 1)
    assert f("refurb", "CMH", RENEWAL, 0, CMH).kg == 79
    assert f("redeploy", "CMH", {"kind": "proj", "id": "p", "other_site": False}, 0, CMH).kg == 83.5
    assert f("release", "CMH", None, 0, CMH).kg == 41  # no named order: d 0.5, 42.5 - 1.5
    assert f("harvest", "CMH", {"kind": "wo", "id": "r"}, 3, CMH).kg == round(3 * 85 * 0.08 - 2, 1)


def test_tf_13_without_a_factor_there_is_no_figure():
    assert tool_carbon.co2_avoided("release", "ZZZ", RENEWAL, 0, CMH) is None
    assert tool_carbon.co2_avoided("release", "CMH", RENEWAL, 0, {}) is None
    assert tool_carbon.co2_avoided("nowhere", "CMH", RENEWAL, 0, CMH) is None


def test_tf_13_the_pack_holds_a_versioned_reviewed_table():
    t = load_pack("tool_fleet").valuer.params["co2"]
    assert t["version"] == "tf-co2-2026.1" and t["source"] and t["year"] and t["legal_review"] == "pending"
    need = {"embodied_new_kg", "mass_kg", "prep_kg", "refurb_kg", "teardown_kg", "recycle_credit_kg_per_kg", "treat_kg",
            "road_kg_per_tkm", "lane_km"}  # fmt: skip
    assert set(t["classes"]) >= {"CMH", "BRK", "DCD", "CRH"}
    assert all(need <= set(v) for v in t["classes"].values())


# ------------------------------------------------------------------ the panel and the certificate
@pytest.fixture(scope="module", autouse=True)
def world():
    starting.reset()
    assert call("org.create", {"id": ORG, "parent_id": "workspace", "kind": "company", "name": "Tool fleet CO2"}, "admin")["ok"]
    yield
    starting.reset()


def _open(serial: str) -> str:
    from di.services.cases import intake
    from tests.helpers import tool_case_facts

    with SessionLocal() as s:
        c = intake.open_case(
            s, {"org_unit_id": ORG, "template_key": "tool_fleet", "asset_key": serial, "reason": "contract_end",
                "facts": tool_case_facts(serial, {"tool_class": "CMH", "site": "Houston", "grade": "A"})}, "system")  # fmt: skip
        s.commit()
        return c["id"]


def test_tf_13_routes_carry_co2():
    cid = _open("CMH-70101")
    r = client.get(f"/api/screens/toolfleet/{cid}", headers=h("admin"))
    assert r.status_code == 200, r.text
    v = r.json()
    ok = [p for p in v["paths"] if p["ok"]]
    assert ok and all(p["co2"] and p["co2"] != 0 for p in ok)
    assert all(p["co2Source"] == "sample factors tf-co2-2026.1" for p in v["paths"] if p["co2"] is not None)
    assert v["co2"]["version"] == "tf-co2-2026.1" and v["co2"]["legal_review"] == "pending"


def test_tf_13_recycle_cannot_close_without_certificate():
    from di.services.actions import execution

    case = {"template": "tool_fleet", "chosen": {"id": "exit"}, "exec": {"steps": [{"k": "custody", "ack": None}]}}
    assert "certificate" in execution.recycling_refusal(case)
    case["exec"]["steps"][0]["ack"] = {"ref": "CERT-1", "sim": True}
    assert execution.recycling_refusal(case)  # a simulated acknowledgement is not the recycler's certificate
    case["exec"]["steps"][0]["ack"] = {"ref": "CERT-1", "sim": False}
    assert execution.recycling_refusal(case) is None
    assert execution.recycling_refusal({**case, "chosen": {"id": "release"}, "exec": {"steps": []}}) is None
    assert execution.recycling_refusal({**case, "template": None, "exec": {"steps": []}}) is None
    assert execution.RECYCLING_TEXT == "Recycling needs the recycler's certificate before the case closes (GR-06)"


def test_tf_13_outcome_confirm_is_refused_until_the_certificate_is_acknowledged():
    """Through the pipeline: a closed `exit` case with an unacknowledged custody step is refused with the GR-06 text."""
    from di.services.actions import execution
    from di.services.cases import store

    cid = _open("CMH-70102")
    with SessionLocal() as s:
        c = store.get(s, cid, for_update=True)
        c["chosen"] = next(r for r in c["routes"] if r["id"] == "exit")
        c["stage"] = "closed"
        c["exec"] = {"ref": "AP-T", "decisionId": "D-T", "instruction": 1, "approver": "approver",
                     "steps": [{"k": "custody", "sys": "Recycler", "state": "done", "ack": None}]}  # fmt: skip
        store.save(s, c)
        s.commit()
    out = call("outcome.confirm", {"case_id": cid}, "finance")
    assert not out["ok"] and execution.RECYCLING_TEXT in str(out), out


def test_tf_13_co2_does_not_change_net():
    """Every path of every golden tool-fleet decision keeps its net now that the CO2e line is carried."""
    from di.core import golden
    from di.services.modeler.valuers import tool_fleet

    want = golden.load("po/equip_decisions")
    cases = {c["id"]: c for c in tool_fleet.sample_queue()}
    checked = 0
    for w in want["decisions"]:
        got = tool_fleet.decide(cases[w["id"]], tool_fleet.BASEP, want["rules"])
        nets = {p["k"]: p["net"] for p in got["all"]}
        for p in w["paths"]:
            assert nets[p["k"]] == pytest.approx(p["net"], abs=1e-6), (w["id"], p["k"])
            checked += 1
    assert checked >= 6 * len(want["decisions"]) - 1

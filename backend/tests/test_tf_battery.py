"""Plan 9, P9-3.19 (TF-16): a battery pack is valued as its own class, by the pure valuer `battery.decide` (never a model).

The sample world's six classes and the PO goldens stay as they were; the pack's G-BAT-1, G-BAT-4 and G-BAT-5 gates apply to a
`BAT` case only; `decide_case` sends a `BAT` case to the battery valuer.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal, engine
from di.services.cases import intake, store, tool_queue
from di.services.cases.decide import decide_case
from di.services.modeler import gates as gate_catalogue
from di.services.modeler.compile import FlowVersion
from di.services.modeler.pack import load_pack
from di.services.modeler.valuers import battery, tool_fleet, tool_inputs
from tests import starting
from tests.helpers import tool_case_facts

AS_OF = datetime(2026, 11, 2, tzinfo=UTC)
PARAMS = load_pack("tool_fleet").valuer.params["battery"]
POOL = {
    "kind": "proj",
    "id": "TPR-9",
    "who": "Houston service center",
    "site": "Houston",
    "need": 14,
    "rental": 140,
    "quote": "PR-9",
}
LEASE = {
    "kind": "lease",
    "id": "FC-BAT-1",
    "who": "Brightline Mechanical",
    "site": "Houston",
    "need": 20,
    "rate": 11,
    "term": 12,
    "renew": False,
}


def _case(soh: float | None, *, damaged: bool = False, lease: bool = False, pool: bool = False) -> dict:
    return {
        "id": "BT-1", "cls": "BAT", "site": "Houston", "soh": soh, "sohRead": "2026-10-28", "damaged": damaged,
        "dem": {"lease": [LEASE] if lease else [], "so": [], "bid": [], "proj": POOL if pool else None, "rcq": "RQ-77"},
    }  # fmt: skip


def _by(d, k):
    return next(x for x in d["all"] if x["k"] == k)


def test_tf_16_battery_take_back_with_hazard_line():
    d = battery.decide(_case(62, lease=True, pool=True), PARAMS)
    assert [x["k"] for x in d["all"]] == ["release", "redeploy", "resell", "exit"]
    assert [x["k"] for x in d["all"] if x["ok"]] == ["exit"] and d["best"]["k"] == "exit"
    labels = [x["label"] for x in _by(d, "exit")["lines"]]
    assert "Material credit (cells)" in labels
    assert "Hazardous transport (lithium-ion, UN 3480)" in labels and "Take-back scheme fee" in labels
    assert "Damaged-battery packaging" not in labels
    assert _by(d, "exit")["dest"]["name"] == "Take-back recycling"


def test_tf_16_healthy_battery_to_pool():
    d = battery.decide(_case(76, pool=True), PARAMS)
    assert d["best"]["k"] == "redeploy" and not _by(d, "release")["ok"]  # release needs 80% and a named order
    assert _by(d, "resell")["ok"] and d["uplift"] >= 0 and d["dk"] == "exit"
    assert battery.decide(_case(85, lease=True), PARAMS)["best"]["k"] == "release"


def test_tf_16_damaged_never_resold():
    d = battery.decide(_case(85, damaged=True, lease=True, pool=True), PARAMS)
    resell = _by(d, "resell")
    assert not resell["ok"] and resell["why"].startswith("Damaged battery transport")
    assert "Damaged-battery packaging" in [x["label"] for x in _by(d, "exit")["lines"]]
    assert d["best"]["k"] == "exit"  # no standard lane for a damaged pack
    assert _by(battery.decide(_case(None), PARAMS), "exit")["ok"] and battery.decide(_case(None), PARAMS)["best"]["k"] == "exit"


def test_tf_16_sample_world_untouched():
    assert tool_fleet.CK == ["CMH", "BRK", "DCD", "CRH", "AGR", "LSR"]
    assert "BAT" not in tool_fleet.CLS


def test_tf_16_gates_apply_to_a_battery_case_only():
    pack = load_pack("tool_fleet")
    ids = lambda c: [r.gate_id for r in gate_catalogue.evaluate_gates(c, pack, AS_OF)]  # noqa: E731
    assert not {"G-BAT-1", "G-BAT-4", "G-BAT-5"} & set(ids({"cls": "CMH", "battery": {"rechargeable": True, "damaged": True}}))
    got = {r.gate_id: r for r in gate_catalogue.evaluate_gates(battery.gate_facts(_case(62, damaged=True)), pack, AS_OF)}
    assert {"G-BAT-1", "G-BAT-4", "G-BAT-5"} <= set(got) and not got["G-BAT-5"].passed


def test_tf_16_decide_case_sends_bat_to_the_battery_valuer():
    d = decide_case(
        _case(76, pool=True) | {"evidenceRecords": battery.sample_evidence(76, AS_OF)},
        load_pack("tool_fleet"),
        FlowVersion(None, 1, ()),
        AS_OF,
    )
    assert d.route == "redeploy" and [r["id"] for r in d.routes] == ["release", "redeploy", "resell", "exit"]
    assert next(r for r in d.routes if r["id"] == "exit")["plan"] == "Take-back recycling"
    no_permit = decide_case(_case(76, pool=True), load_pack("tool_fleet"), FlowVersion(None, 1, ()), AS_OF)
    assert next(r for r in no_permit.routes if r["id"] == "exit")["excluded"]  # G-BAT-5: a permitted recycler is on file first


def test_tf_16_state_of_health_from_telematics_evidence():
    from di.services.modeler.evidence import Evidence

    e = Evidence("battery_soh", "tooltel", AS_OF, "pass", {"soh_pct": 71.5, "read_at": "2026-10-30", "damaged": False})
    c = tool_inputs.battery_case({"id": "BT-2", "cls": "BAT", "dem": {}}, {"battery_soh": e})
    assert c["soh"] == 71.5 and c["sohRead"] == "2026-10-30" and c["damaged"] is False
    assert tool_inputs.battery_case({"id": "BT-3", "cls": "BAT"}, {})["soh"] is None  # nothing is assumed

# ------------------------------------------------------------------ a battery case opened from data (P9-3.19 follow-up)
KEYS = ["BAT-48001", "CMH-48213", "FC-TEST"]


def _clean() -> None:
    with engine.begin() as conn:
        for m in ("contract_line", "contract", "condition"):
            for t in ("provenance", "canonical"):
                conn.execute(text(f"DELETE FROM {t} WHERE model = :m AND key = ANY(:k)"), {"m": m, "k": KEYS})  # noqa: S608


@pytest.fixture
def world(no_synced_demand):
    starting.reset()
    _clean()
    yield
    starting.reset()
    _clean()


def _open(serial: str, facts: dict) -> dict:
    with SessionLocal() as s:
        c = intake.open_case(
            s,
            {"org_unit_id": "Customer A", "template_key": "tool_fleet", "asset_key": serial, "reason": "manual",
             "facts": tool_case_facts(serial, facts)},
            "system",
        )  # fmt: skip
        s.commit()
    return c


def test_tf_16_a_battery_case_opens_end_to_end(world):
    c = _open("BAT-48001", {"cls": "BAT", "site": "Houston", "soh": 76, "sohRead": "2026-10-28", "dem": {"proj": POOL}})
    assert c["cls"] == "BAT" and c["valuer"]["soh"] == 76
    assert [r["id"] for r in c["routes"]] == ["release", "redeploy", "resell", "exit"]
    by = {r["id"]: r for r in c["routes"]}
    assert "Battery state of health" in by["redeploy"]["failReason"] and by["redeploy"]["excluded"]  # G-BAT-1: no reading on file
    assert c["recommendation"]["id"] == "resell"  # the one path the gates leave open
    assert next(r for r in c["routes"] if r["id"] == "exit")["excluded"]  # G-BAT-5: no permitted recycler on file
    with SessionLocal() as s:
        assert store.get(s, c["id"])["recommendation"]["id"] == "resell"
        assert tool_queue.open_queue(s, "Customer A") == []  # a pack is not planned in the tools' queue


def test_tf_16_a_battery_case_leaves_the_tools_queue_as_it_was(world):
    tool = {"cls": "CMH", "grade": "B", "ft": "Repair center", "site": "Houston", "rul": 60, "dem": {"lease": [LEASE]}}
    alone = _open("CMH-48213", tool)
    before = (alone["recommendation"]["id"], alone["recommendation"]["net"])
    _open("BAT-48001", {"cls": "BAT", "site": "Houston", "soh": 85, "sohRead": "2026-10-28", "dem": {"lease": [LEASE]}})
    with SessionLocal() as s:
        plan = tool_queue.plan_of(s, "Customer A")
        again = store.get(s, alone["id"])
    assert set(plan["res"]) == {alone["id"]}  # the pack is not in the plan, the tool is planned as before
    assert (again["recommendation"]["id"], again["recommendation"]["net"]) == before

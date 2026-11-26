"""P9-12.8 (stories NS-CORE-01 and NS-CORE-03): core acceptance with a credit, and a fraud hold that only a person releases.

NS-CORE-01: `check_core_acceptance` (gate CORE-ACCEPT, di.services.modeler.gate_checks.core) gives each returned core a credit
from the pack's acceptance criteria per part number: `full` when every required check passes, `partial` (50 %) when only a check
the part allows to fail does, `none` otherwise (the failed checks are named, and remanufacturing is closed to that core).
NS-CORE-03: the X-15 triage (di.services.modeler.fraud) reads the part family and the dealer's rejects from the core returns
system (source `core_ret`); a signal holds the case at intake for a person (`fraud.hold`), and only a person releases it.
The cores are the ones the mock `core_ret` serves (source-sim/sim/vendors/core_returns, built here as literals), the adapter's
`map` run on them. Synthetic data throughout. Credit and fraud rules are commercial matters: Kinective's Legal team reviews them.
"""

import copy
import json
from typing import Any

import pytest
from sqlalchemy import text

from di.connectors.base import Record
from di.connectors.registry import ADAPTERS
from di.core.db import SessionLocal, engine
from di.services.agents import chain, runtime
from di.services.cases import store
from di.services.cases.decide import decide_case
from di.services.modeler.compile import FlowVersion
from di.services.modeler.gate_checks.core import SOURCE, core_credit, fraud_evidence
from di.services.modeler.gates import evaluate_gates
from di.services.modeler.pack import PACKS_DIR, load_pack
from tests import starting
from tests.helpers import call, client, h

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")

ALL = {"housing_intact": True, "no_cracks": True, "complete": True, "family_match": True}


def _core(core_id: str, dealer: str = "D-02", observed: str = "ALT-1450", rejects: dict | None = None, **checks: bool) -> dict:
    """A core as the mock serves it, with the dealer's recent rejects (`dealerRejects`, window in days -> count)."""
    return {
        "coreId": core_id, "dealerId": dealer, "declaredPartNumber": "ALT-1450", "observedPartNumber": observed,
        "deposit": 85, "checks": ALL | checks, "receivedAt": "2026-11-20T09:00:00+00:00",
        "dealerRejects": rejects or {"30": 0, "90": 0},
    }  # fmt: skip


FULL = _core("C-0001")
PARTIAL = _core("C-0002", complete=False)  # the bracket is missing
CRACKED = _core("C-0003", no_cracks=False)
MISMATCH = _core("C-0004", dealer="D-05", observed="STR-2210", family_match=False)
REPEAT = _core("C-0005", dealer="D-17", rejects={"30": 1, "90": 3})


def _case(core: dict) -> dict[str, Any]:
    return {"id": f"CORE-{core['coreId']}", "template": "auto_core", "family": "alternator", "deposit": 85, "core": core}


def _credit(core: dict) -> dict[str, Any]:
    return core_credit(core, load_pack("auto_core"))


# ---------------------------------------------------------------- NS-CORE-01: acceptance and credit
def test_ns_core_01_acceptance_full_partial_none():
    assert _credit(FULL) == {"credit": "full", "pct": 100, "failed": []}
    assert _credit(PARTIAL) == {"credit": "partial", "pct": 50, "failed": ["complete"]}
    assert _credit(CRACKED) == {"credit": "none", "pct": 0, "failed": ["no_cracks"]}
    pack = load_pack("auto_core")
    by = {c["coreId"]: evaluate_gates(_case(c), pack) for c in (FULL, PARTIAL, CRACKED)}
    [full], [partial], [none] = by.values()
    assert (full.gate_id, full.passed) == ("CORE-ACCEPT", True)
    assert partial.passed and "50" in " ".join(partial.disclosures) and "complete" in " ".join(partial.disclosures)
    assert not none.passed and none.effect.kind == "block" and none.effect.routes == ("reman",) and "no_cracks" in none.reason


def test_ns_core_01_two_failures_or_a_required_one_is_none():
    assert _credit(_core("C-9", complete=False, no_cracks=False))["credit"] == "none"  # a check the part does not allow
    assert _credit(_core("C-9", family_match=False))["failed"] == ["family_match"]
    unknown = _core("C-9") | {"declaredPartNumber": "XYZ-1"}  # no criteria for the part number
    assert _credit(unknown)["credit"] == "none"


def test_ns_core_01_a_rejected_core_is_not_remanufactured():
    pack = load_pack("auto_core")
    ok = decide_case(_case(FULL), pack, FlowVersion(None, 1, ()))
    assert ok.route == "reman" and ok.net == pytest.approx(44)  # 120 - 70 - 6
    bad = decide_case(_case(CRACKED), pack, FlowVersion(None, 1, ()))
    reman = next(r for r in bad.routes if r["id"] == "reman")
    assert reman["excluded"] and "no_cracks" in reman["failReason"]
    assert bad.route == "harvest" and bad.net == pytest.approx(28)  # 40 - 12


def test_ns_core_01_the_adapter_maps_a_core_to_facts():
    adapter: Any = ADAPTERS["core_ret"]
    rec = Record("cores", "C-0003", {**CRACKED, "org_unit_id": "Customer A"}, "http://source-sim/core-returns/api/cores")
    facts = {(f.model, f.field): f.value for f in adapter.map(rec)}
    assert facts[("condition", "core_checks")] == CRACKED["checks"]
    assert facts[("asset", "declared_part_number")] == "ALT-1450" and facts[("asset", "dealer_id")] == "D-02"
    assert facts[("market", "core_deposit")] == 85


# ---------------------------------------------------------------- NS-CORE-03: fraud holds for a person
def _clean() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM agent_run_step"))
        conn.execute(text("DELETE FROM agent_run"))
        conn.execute(text("DELETE FROM agent_proposal"))
        conn.execute(text("DELETE FROM work_item"))
        conn.execute(text("DELETE FROM pack_version"))
        conn.execute(text("DELETE FROM customer_overlay"))


@pytest.fixture
def fresh():
    starting.reset()
    _clean()
    doc: dict[str, Any] = copy.deepcopy(json.loads((PACKS_DIR / "auto_core.json").read_text(encoding="utf-8")))
    doc["version"] = "1.9.2"  # the shipped pack, imported and published as the org's
    pid = _ok(call("pack.import", {"doc": doc}, "admin"))["id"]
    _ok(call("pack.submit", {"id": pid}, "admin"))
    _ok(call("pack.approve", {"id": pid}, "approver"))
    yield
    _clean()
    starting.reset()


def _ok(r: dict) -> dict:
    assert r.get("ok"), r
    return r["output"]


def _open(asset: str, core: dict) -> str:
    body = {"org_unit_id": "Customer A", "template_key": "auto_core", "asset_key": asset, "reason": "manual",
            "facts": {"family": "alternator", "deposit": 85}}  # fmt: skip
    cid = _ok(call("case.open", body, "planner-a"))["case_id"]
    with SessionLocal() as s:
        c = store.get(s, cid, for_update=True)
        assert c is not None
        c["core"] = core
        c["evidenceRecords"] = [*(c.get("evidenceRecords") or []), *fraud_evidence(core)]
        store.save(s, c)
        s.commit()
    return str(cid)


def _case_now(cid: str) -> dict[str, Any]:
    with SessionLocal() as s:
        c = store.get(s, cid)
    assert c is not None
    return c


def _intake(cid: str) -> chain.StageRecord:
    with SessionLocal() as s:
        run_id = runtime.start(s, "recover-chain", "stage_chain", cid, account="planner-a")
        s.commit()
        runtime.run_until_blocked(s, run_id, max_steps=9)
    with SessionLocal() as s:
        return {r.stage: r for r in chain.records_of(s, run_id)}["intake"]


def _prepared(action: str, body: dict, user: str = "approver", agent: str = "coordinator") -> dict:
    return client.post(f"/api/actions/{action}", json=body, headers=h(user) | {"X-Circularity-Preparer": agent}).json()


def _held_with(cid: str, signal: str) -> dict[str, Any]:
    rec = _intake(cid)
    assert rec.status == "held" and rec.output["fraud"]["held"] is True
    f = _case_now(cid)["fraud"]
    assert f["status"] == "held" and f["rule_version"] == load_pack("auto_core").fraud.version  # type: ignore[union-attr]
    [sig] = f["signals"]
    assert (sig["id"], sig["source"]) == (signal, SOURCE) and SOURCE == "core_ret"
    return f


def test_ns_core_03_family_mismatch_holds(fresh):
    cid = _open("CORE-A-1", MISMATCH)  # declared an alternator, a starter arrived
    f = _held_with(cid, "part_family_mismatch")
    assert f["signals"][0]["value"] == ["model"]
    why = "Checked the photos with the dealer; the part is the declared one."
    refused = _prepared("fraud.release", {"case_id": cid, "reason": why})  # an agent prepared it: never
    assert refused["ok"] is False and refused["error"]["code"] == "approval_required"
    assert _case_now(cid)["fraud"]["status"] == "held"
    assert _ok(call("fraud.release", {"case_id": cid, "reason": why}, "approver"))["status"] == "released"
    assert _case_now(cid)["fraud"]["resolved_by"] == "approver"


def test_ns_core_03_repeat_returner_holds(fresh):
    cid = _open("CORE-A-2", REPEAT)  # dealer D-17: three rejected cores in 90 days
    f = _held_with(cid, "repeat_returner")
    assert f["signals"][0]["value"] == 3


def test_ns_core_03_a_clean_core_is_not_held(fresh):
    cid = _open("CORE-A-3", FULL)
    rec = _intake(cid)
    assert rec.status == "done" and rec.output["fraud"]["held"] is False
    assert _case_now(cid).get("fraud") is None

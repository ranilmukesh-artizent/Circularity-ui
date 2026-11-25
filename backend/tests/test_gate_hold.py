"""P9-1.2 (X-07): a device lot with no data-wipe record is held with its batch; the record landing in the canonical store
enqueues `case.gateRecheck`, and the job releases that lot only. Runs on the evidence fixture pack (the device pack with
G-DEV-WIPE active), put in place of the live pack for the test. Every test ends with the starting state."""

import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from di import worker
from di.core.db import SessionLocal
from di.services.canonical import store as canonical
from di.services.canonical.schema import check_fact, compliance_asset, compliance_key
from di.services.canonical.store import Fact
from di.services.cases import gate_hold, intake, store
from di.services.modeler.pack import Pack, load_pack, parse_pack
from tests import starting
from tests.helpers import client, h

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "packs" / "evidence_test.json"
LOT = {"brand": "Apple", "model": "iPhone 14", "band": "25-48m", "grade": "B", "ref": 315, "qty": 40, "doh": 12}
WIPE_AT = "2026-10-01T08:00:00Z"


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    _clean()
    starting.reset()
    pack: Pack = parse_pack(json.loads(FIXTURE.read_text(encoding="utf-8")))
    monkeypatch.setattr(
        gate_hold, "default_pack_of", lambda case: pack if case.get("template") == "device" else load_pack(case["template"])
    )
    yield
    _clean()
    starting.reset()


def _clean() -> None:
    with SessionLocal() as s:
        s.execute(text("DELETE FROM provenance WHERE model = 'compliance'"))
        s.execute(text("DELETE FROM canonical WHERE model = 'compliance'"))
        s.commit()


def _open(asset: str, batch: str | None = "B-7") -> str:
    facts = LOT | ({"batch": batch} if batch else {})
    with SessionLocal() as s:
        c = intake.open_case(s, {"org_unit_id": "Customer A", "template_key": "device", "asset_key": asset, "reason": "manual",
                                 "facts": facts}, "admin")  # fmt: skip
        s.commit()
    return str(c["id"])


def _get(cid: str) -> dict[str, Any]:
    with SessionLocal() as s:
        c = store.get(s, cid)
    assert c is not None
    return c


def _wipe(asset: str, result: str = "pass", type: str = "data_wipe", at: str = WIPE_AT) -> None:
    key = compliance_key(asset, type)
    row = {"asset_key": asset, "type": type, "result": result, "method": "purge", "tool": "wipe-tool 4.2", "ref": "WC-" + asset,
           "at": at, "operator": "bench-3", "value": {"imei": "35-" + asset}}  # fmt: skip
    with SessionLocal() as s:
        canonical.apply(s, "manual", [Fact("compliance", key, f, v) for f, v in row.items()])
        s.commit()


def _recheck_jobs() -> list[dict[str, Any]]:
    with SessionLocal() as s:
        rows = s.execute(text("SELECT payload, dedupe_key FROM job WHERE kind = 'case.gateRecheck' AND status = 'queued'")).all()
    return [{"payload": p, "dedupe_key": k} for p, k in rows]


def _run_rechecks() -> None:
    for j in _recheck_jobs():
        worker.HANDLERS["case.gateRecheck"](j["payload"])
    with SessionLocal() as s:
        s.execute(text("DELETE FROM job WHERE kind = 'case.gateRecheck'"))
        s.commit()


def test_x_07_lot_without_wipe_is_held():
    cid = _open("LOT-W1")
    c = _get(cid)
    assert c["stage"] == "none" and c["recommendation"] is None and c["batchRef"] == "B-7"
    assert c["gateHold"]["gates"] == ["G-DEV-WIPE"] and c["gateHold"]["batch"] == "B-7"
    assert all(r["excluded"] and r["failReason"] == "Data-wipe certificate: Data-wipe certificate missing" for r in c["routes"])
    (g,) = c["gates"]
    assert (g["id"], g["type"], g["stageLabel"], g["passed"], g["hold"]) == ("G-DEV-WIPE", "Compliance", "Condition", False, True)
    assert g["routeNames"] and g["reason"] == "Data-wipe certificate missing" and g["owner"] == "Compliance"
    assert "requiredSteps" not in c


def test_x_07_batch_auto_release():
    ids = [_open(f"LOT-W{i}") for i in (1, 2, 3)]
    with SessionLocal() as s:
        assert gate_hold.batch_status(s, "B-7") == {"total": 3, "held": 3, "released": 0}
    _wipe("LOT-W2")
    assert _recheck_jobs() == [{"payload": {"asset_key": "LOT-W2"}, "dedupe_key": "case.gateRecheck:LOT-W2"}]
    _run_rechecks()
    one, two, three = (_get(i) for i in ids)
    assert two["gateHold"] is None and two["stage"] == "awaiting_approval" and two["recommendation"] is not None
    assert [g["passed"] for g in two["gates"]] == [True]
    assert two["gates"][0]["evidence"][0]["source"] == "manual"
    assert one["gateHold"] is not None and three["gateHold"] is not None and one["stage"] == three["stage"] == "none"
    with SessionLocal() as s:
        log = s.execute(
            text("SELECT from_stage, to_stage, reason, actor FROM case_stage_log WHERE case_id = :c ORDER BY id"), {"c": ids[1]}
        ).all()
        assert gate_hold.batch_status(s, "B-7") == {"total": 3, "held": 2, "released": 1}
    assert log[-1][:2] == ("none", "awaiting_approval") and log[-1][3] == "system"
    assert log[-1][2] == "Released: Data-wipe certificate from manual at 2026-10-01 08:00 UTC"
    # the lot is released, not approved: a person still decides
    assert two.get("approval") is None


def test_x_07_failed_wipe_adds_step():
    cid = _open("LOT-W4")
    _wipe("LOT-W4", "fail")
    _run_rechecks()
    c = _get(cid)
    assert c["gateHold"] is not None and c["stage"] == "none"
    assert c["requiredSteps"] == [{"gate": "G-DEV-WIPE", "step": "Re-run the wipe or destroy the storage", "owner": "Compliance"}]
    assert c["gates"][0]["reason"] == "Data-wipe certificate failed verification"
    _wipe("LOT-W4", "pass", at="2026-10-02T08:00:00Z")  # the re-run passes: released, the step is gone
    _run_rechecks()
    c = _get(cid)
    assert c["gateHold"] is None and c["stage"] == "awaiting_approval" and "requiredSteps" not in c


def test_x_07_recheck_leaves_other_assets_alone():
    held = _open("LOT-W5", batch=None)
    with SessionLocal() as s:
        assert gate_hold.recheck(s, "LOT-NONE") == []
        assert gate_hold.recheck(s, "LOT-W5") == []  # no evidence yet: still held
        s.commit()
    c = _get(held)
    assert c["gateHold"] is not None and "batchRef" not in c
    with SessionLocal() as s:
        assert gate_hold.batch_status(s, "B-NONE") == {"total": 0, "held": 0, "released": 0}


def test_x_07_compliance_facts_enqueue_one_recheck_per_asset():
    with SessionLocal() as s:
        facts = [Fact("compliance", compliance_key("LOT-W6", t), "result", "pass") for t in ("data_wipe", "recall_check")]
        facts += [Fact("compliance", compliance_key("LOT-W7", "data_wipe"), "result", "pass")]
        canonical.apply(s, "manual", facts)
        canonical.apply(s, "manual", facts[:1])  # again: the queued job is the same job
        s.commit()
    assert sorted(j["dedupe_key"] for j in _recheck_jobs()) == ["case.gateRecheck:LOT-W6", "case.gateRecheck:LOT-W7"]


def test_x_03_compliance_model_checks_its_fields():
    k = compliance_key("LOT:with:colons", "data_wipe")
    assert k == "LOT:with:colons:data_wipe" and compliance_asset(k) == "LOT:with:colons"
    assert check_fact(Fact("compliance", k, "result", "pass")) is None
    assert check_fact(Fact("compliance", k, "at", "2026-10-01T08:00:00Z")) is None
    assert check_fact(Fact("compliance", k, "valid_until", "soon")) is not None
    assert check_fact(Fact("compliance", k, "color", "red")) == "Unknown field compliance.color"


def test_x_07_case_screen_serves_gates_hold_and_batch():
    ids = [_open(f"LOT-W{i}") for i in (1, 2)]
    _wipe("LOT-W2")
    _run_rechecks()
    r = client.get(f"/api/screens/case/{ids[0]}", headers=h("admin"))
    assert r.status_code == 200, r.text
    c = r.json()["case"]
    assert c["gateHold"]["batch"] == "B-7" and c["batch"] == {"ref": "B-7", "total": 2, "held": 1, "released": 1}
    assert [g["id"] for g in c["gates"]] == ["G-DEV-WIPE"] and c["gates"][0]["passed"] is False
    r = client.get(f"/api/screens/case/{ids[1]}", headers=h("admin"))
    c = r.json()["case"]
    assert c["gateHold"] is None and c["gates"][0]["passed"] is True and c["batch"]["released"] == 1


def test_shipped_templates_open_cases_without_gate_keys():
    facts = {"cls": "CMH", "grade": "B", "ft": "Repair center", "site": "Houston", "rul": 62}
    i = {"org_unit_id": "Customer A", "template_key": "tool_fleet", "asset_key": "T-NOGATE", "reason": "manual", "facts": facts}
    with SessionLocal() as s:
        c = intake.open_case(s, i, "admin")
        s.commit()
    got = _get(str(c["id"]))
    assert got["stage"] == "awaiting_approval" and got["recommendation"] is not None
    assert not {"gates", "gateHold", "requiredSteps", "evidenceRecords", "batchRef"} & set(got)

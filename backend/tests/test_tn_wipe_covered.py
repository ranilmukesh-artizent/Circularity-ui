"""Plan 9, P9-10.7 (stories TN-06, TN-09 and TN-10): the configuration wipe gate G-NET-CFG, the covered-equipment gate G-NET-COV
and the bench read on the case.

A unit's wipe certificate is the test bench's (`tn_bench`) read, never typed or computed here: without a verified wipe that
covers configuration, credentials, keys and logs every route fails and the unit is held, `EX-TN-CFG` opens for the test bench
lead (Engineer); a wipe that failed twice also requires the step `destroy_storage` and fails `resell` with its own text. A
unit of a covered manufacturer under the reimbursement programme in the listed region may only be disposed of: the other four
routes fail and recycling requires the disposal record. The case shows the bench's own counts, firmware and certificate with
source and age. Facts are written by the real adapters' mapping on literal records (no source-sim). Legal note: the wipe
standard and the covered-equipment rules are the pack's data; Kinective's Legal team reviews them before they are relied on.
"""

from typing import Any

import pytest
from sqlalchemy import text

from di import worker
from di.core.db import SessionLocal
from di.services.agents.forbidden import forbidden
from di.services.agents.stages import condition
from di.services.canonical.schema import serial_key
from di.services.cases import bench_evidence, intake, store
from di.services.engine.routes import mk_route, term
from di.services.modeler.gate_checks.network import check_config_wipe
from di.services.modeler.gates import apply_gate_results, pack_gates
from di.services.modeler.pack import load_pack
from tests.test_tn_intake import _bench, _case, _element, _items, _job, _ok, _open, _write, fresh, sn  # noqa: F401

DEST = "Wipe failed twice: storage destroyed, no resale"
MISSING = "Configuration wipe certificate missing or failed"
COVERED = "Covered equipment: dispose only"
ROUTES = ("redeploy", "spare", "resell", "harvest", "recycle")
NONE = {"status": "none", "attempts": 0, "scope": [], "verifiedAt": None, "certificateRef": None}
FAILED = {"status": "failed", "scope": [], "verifiedAt": None, "certificateRef": None}


def _unit(n: int, wipe: dict[str, Any] | None = None, bench: bool = True, **element: Any) -> dict[str, Any]:
    """A removed unit the inventory knows, with the bench's result (none at all with `bench=False`); returns its job unit."""
    (u,) = _job("RJ-02", f"SITE-{100 + n}", [(n, "RRU-4410")])
    _write("tn_decom", "removal_jobs", u)
    _write("tn_inv", "elements", _element(n, "RRU-4410", u["siteId"], **element))
    if bench:
        _write("tn_bench", "results", _bench(n, wipe))
    return u


def _gate(c: dict[str, Any], gid: str) -> dict[str, Any]:
    return next(g for g in c["gates"] if g["id"] == gid)


def _route(c: dict[str, Any], rid: str) -> dict[str, Any]:
    return next(r for r in c["routes"] if r["id"] == rid)


def _pure(wipe: dict[str, Any] | None) -> tuple[Any, Any]:
    """The wipe gate's result for a case that carries the bench's evidence of that wipe, and the routes it was applied to."""
    pack = load_pack("telecom_network")
    gate = next(g for g in pack_gates(pack) if g.id == "G-NET-CFG")
    records = bench_evidence.evidence({"wipe": wipe} if wipe else None)
    case = {"id": "RT-9001", "template": "telecom_network", "evidenceRecords": records}
    res = check_config_wipe(case, pack, gate)
    routes = [mk_route({"id": r.id, "plan": r.id, "terms": [term("Sale", 100, "gain")]}) for r in pack.routes]
    apply_gate_results(routes, [res])
    return res, {r["id"]: r for r in routes}


def _recheck() -> None:
    with SessionLocal() as s:
        jobs = s.execute(text("SELECT payload FROM job WHERE kind = 'case.gateRecheck' AND status = 'queued'")).scalars().all()
    for p in jobs:
        worker.HANDLERS["case.gateRecheck"](p)
    with SessionLocal() as s:
        s.execute(text("DELETE FROM job WHERE kind = 'case.gateRecheck'"))
        s.commit()


def _item(cid: str, kind: str) -> list[dict[str, Any]]:
    with SessionLocal() as s:
        rows = s.execute(
            text("SELECT status, owner_role, action, outcome FROM work_item WHERE case_id = :c AND type = :t ORDER BY id"),
            {"c": cid, "t": kind},
        ).mappings().all()  # fmt: skip
    return [dict(r) for r in rows]


def test_tn_06_resell_fails_with_its_own_text_after_two_failed_wipes():
    twice = {"status": "failed", "attempts": 2, "scope": [], "certificate": None, "verifiedAt": None}
    res, routes = _pure(twice)
    assert res.passed is False and res.effect.step == "destroy_storage" and res.reason == MISSING
    assert routes["resell"]["failReason"] == f"Configuration wipe certificate: {DEST}"
    assert all(MISSING in routes[r]["failReason"] for r in ("redeploy", "spare", "harvest", "recycle"))
    once, routes = _pure(twice | {"attempts": 1})
    assert once.effect.step is None and MISSING in routes["resell"]["failReason"]
    assert _pure(None)[0].passed is False and _pure(None)[0].effect.step is None


@pytest.mark.parametrize("wipe", [NONE, None])
def test_tn_06_no_wipe_blocks_every_route(wipe):
    u = _unit(21, wipe, bench=wipe is not None)  # a wipe of status none, and a unit the bench never saw
    c = _case(_ok(_open(u))["case_id"])
    gate = _gate(c, "G-NET-CFG")
    assert gate["passed"] is False and gate["hold"] is True and sorted(gate["routes"]) == sorted(ROUTES)
    assert gate["reason"] == MISSING and gate["missing"] == ["Configuration-wipe certificate"]
    assert c["gateHold"] is not None and c["recommendation"] is None
    assert all(_route(c, rid)["excluded"] for rid in ROUTES)  # no route is valued
    (item,) = _item(c["id"], "EX-TN-CFG")
    assert (item["status"], item["owner_role"], item["action"]) == ("open", "Engineer", "Re-run the wipe; units held")
    assert not [s for s in c.get("requiredSteps") or [] if s["gate"] == "G-NET-CFG"]  # no step: nothing failed twice
    assert forbidden("work.resolve")  # an agent never clears the exception
    # the wipe is re-run and verified: the unit is released on its own and the exception closes
    _write("tn_bench", "results", _bench(21))
    _recheck()
    got = store_case(c["id"])
    assert _gate(got, "G-NET-CFG")["passed"] is True and got["gateHold"] is None
    (done,) = _item(c["id"], "EX-TN-CFG")
    assert done["status"] == "done" and done["outcome"] == "released"


def test_tn_06_an_incomplete_scope_does_not_clear():
    u = _unit(22, {"scope": ["configuration", "credentials"]})
    c = _case(_ok(_open(u))["case_id"])
    gate = _gate(c, "G-NET-CFG")
    assert gate["passed"] is False and gate["reason"] == MISSING and c["gateHold"] is not None
    (item,) = _item(c["id"], "EX-TN-CFG")
    assert item["status"] == "open"


def test_tn_06_failed_twice_destroy_and_no_resale():
    u = _unit(15, FAILED | {"attempts": 2})  # SN-TN-0015, the bench's unit whose wipe failed twice
    c = _case(_ok(_open(u))["case_id"])
    assert c["serial"] == "SN-TN-0015"
    steps = [s for s in c["requiredSteps"] if s["gate"] == "G-NET-CFG"]
    assert [s["step"] for s in steps] == ["destroy_storage"]
    gate = _gate(c, "G-NET-CFG")
    assert gate["passed"] is False and gate["reason"] == MISSING and sorted(gate["routes"]) == sorted(ROUTES)
    assert all(_route(c, rid)["excluded"] for rid in ROUTES)  # nothing moves until a verified wipe
    assert c["gateHold"] is not None and c["gateHold"]["gates"] == ["G-NET-CFG"]
    # a verified wipe (the storage was replaced and the unit wiped again) clears the step and releases the unit
    _write("tn_bench", "results", _bench(15))
    _recheck()
    got = store_case(c["id"])
    assert _gate(got, "G-NET-CFG")["passed"] is True and got["gateHold"] is None
    assert not [s for s in got.get("requiredSteps") or [] if s["gate"] == "G-NET-CFG"]


def test_tn_06_failed_once_is_not_destroyed():
    u = _unit(14, FAILED | {"attempts": 1})  # SN-TN-0014
    c = _case(_ok(_open(u))["case_id"])
    assert _gate(c, "G-NET-CFG")["passed"] is False
    assert not [s for s in c.get("requiredSteps") or [] if s["step"] == "destroy_storage"]


COV = {"manufacturer": "MFR-COV-1", "region": "US"}


def test_tn_09_covered_equipment_dispose_only():
    u = _unit(6, **COV)  # TN-S6: a covered manufacturer under the programme, US; wiped and in the inventory
    u["programme"] = "reimbursement_programme"
    c = _case(_ok(_open(u))["case_id"])
    gate = _gate(c, "G-NET-COV")
    assert gate["passed"] is False and gate["hold"] is False
    assert sorted(gate["routes"]) == ["harvest", "redeploy", "resell", "spare"]  # recycle is the one route left
    assert gate["reason"] == COVERED
    assert all(_route(c, rid)["excluded"] for rid in gate["routes"])
    steps = [s["step"] for s in c["requiredSteps"] if s["gate"] == "G-NET-COV"]
    assert steps == ["disposal_record"]  # recycle requires the disposal record
    assert c.get("gateHold") is None  # a covered unit is not held: it is disposed of


@pytest.mark.parametrize(
    ("element", "programme"),
    [
        ({"manufacturer": "MFR-B", "region": "US"}, "reimbursement_programme"),  # not a covered manufacturer
        (COV, "decommission"),  # another programme
        ({"manufacturer": "MFR-COV-2", "region": "EU"}, "reimbursement_programme"),  # another region
    ],
)
def test_tn_09_not_covered_is_not_blocked(element, programme):
    u = _unit(7, **element)
    u["programme"] = programme
    c = _case(_ok(_open(u))["case_id"])
    assert _gate(c, "G-NET-COV")["passed"] is True and _gate(c, "G-NET-COV")["routes"] == []
    assert not [s for s in c.get("requiredSteps") or [] if s["gate"] == "G-NET-COV"]


def store_case(cid: str) -> dict[str, Any]:
    with SessionLocal() as s:
        c = store.get(s, cid)
    assert c is not None
    return c


def test_tn_10_bench_read_not_computed():
    u = _unit(1)  # SN-TN-0001: 18 of 18 passed, firmware 3.2, certificate WC-0001
    c = _case(_ok(_open(u))["case_id"])
    bench = c["bench"]
    assert bench["source"] == "tn_bench" and bench["summary"] == "18 of 18 passed"
    assert (bench["passed"], bench["total"], bench["firmware"]) == (18, 18, "3.2")
    assert bench["wipe"]["certificate"] == "WC-0001" and bench["wipe"]["status"] == "verified"
    facts = {f["fact"]: f for f in bench["facts"]}
    assert (facts["bench_result"]["value"], facts["firmware"]["value"], facts["wipe_certificate"]["value"]) == (
        "18 of 18 passed", "3.2", "WC-0001",
    )  # fmt: skip
    assert all(f["source"] == "tn_bench" and f["at"] and isinstance(f["ageDays"], float) for f in facts.values())
    assert all(k not in bench for k in ("pass", "all_passed", "grade"))  # the platform adds no verdict
    # the stage reads the same facts for the Case page
    shown = condition.output({}, c)
    assert shown["bench"]["summary"] == "18 of 18 passed"
    assert "Wipe certificate" in [x["fact"] for x in condition.sources({}, c)]
    # the bench says 17: the display says 17, and nothing else is computed from it
    _write("tn_bench", "results", _bench(1, tests={"passed": 17, "total": 18}))
    with SessionLocal() as s:
        again = store.get(s, c["id"], for_update=True)
        assert again is not None
        intake.revalue(s, again)
        store.save(s, again)
        s.commit()
    got = store_case(c["id"])
    assert got["bench"]["summary"] == "17 of 18 passed" and got["bench"]["passed"] == 17
    assert _gate(got, "G-NET-CFG")["passed"] is True  # the gates read the wipe, not the counts
    assert serial_key("Customer A", sn(1)) == got["assetId"]


def test_tn_10_a_case_without_bench_shows_none():
    u = _unit(23, bench=False)
    c = _case(_ok(_open(u))["case_id"])
    assert "bench" not in c
    assert condition.output({}, c).get("bench") is None

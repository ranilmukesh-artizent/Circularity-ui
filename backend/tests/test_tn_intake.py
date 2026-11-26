"""Plan 9, P9-10.6 (stories TN-04 and TN-05): one case per serial, and the inventory match gate G-NET-INV.

Each unit of a removal job opens one `telecom_network` case keyed by the serial (`serial_key`), with the removal site, the
removal date and the source, each fact with its source and age; a second event for the serial joins the case. The unit must
be in the network inventory (`tn_inv`) with the same model and the removal site, otherwise the case is held, no route is
valued and `EX-TN-INV` opens for the inventory lead (Warehouse Manager); when the element appears the case resumes on its own
and the exception closes. Facts are written by the real adapters' mapping on literal records (no source-sim). Legal note:
export and covered-equipment rules are the pack's data; Kinective's Legal team reviews them before they are relied on.
"""

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from di import worker
from di.connectors import extra
from di.connectors.base import Record
from di.connectors.registry import ADAPTERS
from di.core.db import SessionLocal, engine
from di.services.agents.forbidden import forbidden
from di.services.canonical import store as canonical
from di.services.canonical.schema import compliance_key, serial_key
from di.services.canonical.store import Fact
from di.services.cases import intake
from di.services.cases import store as cases
from tests import starting
from tests.helpers import call

ORG = "Customer A"
PACK = Path(__file__).resolve().parents[1] / "di" / "services" / "modeler" / "packs" / "telecom_network.json"
OLD = "2026-10-07T09:00:00+00:00"
ACTION = "Field team to confirm serial and site"
ROUTES = ("redeploy", "spare", "resell", "harvest", "recycle")


def sn(n: int) -> str:
    return f"SN-TN-{n:04d}"


def _job(job: str, site: str, units: list[tuple[int, str]]) -> list[dict[str, Any]]:
    """The records of a removal job as the tracker adapter yields them: one per unit."""
    return [
        {"jobId": job, "siteId": site, "removedAt": "2026-10-04T08:00:00+00:00", "programme": "5G refresh",
         "serial": sn(n), "model": model, "org_unit_id": ORG}
        for n, model in units
    ]  # fmt: skip


def _element(n: int, model: str, site: str, **over: Any) -> dict[str, Any]:
    """An inventory element as the inventory serves it."""
    return {
        "serial": sn(n), "model": model, "partNumber": "PN-4410-02", "hwRevision": "B2", "firmware": "3.1.2",
        "manufacturer": "MFR-B", "site": site, "siteKind": "edge", "region": "North", "status": "removed",
        "exportClassInferred": None, "exportClassConfirmed": None, "org_unit_id": ORG,
    } | over  # fmt: skip


def _clean() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM job WHERE kind = 'case.gateRecheck'"))
        conn.execute(text("DELETE FROM agent_run_step"))
        conn.execute(text("DELETE FROM agent_run"))
        conn.execute(text("DELETE FROM agent_proposal"))
        conn.execute(text("DELETE FROM pack_version"))
        conn.execute(text("DELETE FROM customer_overlay"))
        conn.execute(text("DELETE FROM provenance WHERE key LIKE :p"), {"p": "%:SN-TN-%"})
        conn.execute(text("DELETE FROM canonical WHERE key LIKE :p"), {"p": "%:SN-TN-%"})


def _ok(r: dict) -> dict:
    assert r.get("ok"), r
    return r["output"]


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    _clean()
    doc: dict[str, Any] = copy.deepcopy(json.loads(PACK.read_text(encoding="utf-8")))
    doc["version"] = "1.9.1"  # the shipped pack, imported and published as the org's
    pid = _ok(call("pack.import", {"doc": doc}, "admin"))["id"]
    _ok(call("pack.submit", {"id": pid}, "admin"))
    _ok(call("pack.approve", {"id": pid}, "approver"))
    with SessionLocal() as s:
        for sid in ("tn_inv", "tn_decom"):
            extra.register(s, sid, ORG)
        s.commit()
    yield
    _clean()
    starting.reset()


def _write(source: str, resource: str, payload: dict[str, Any]) -> None:
    with SessionLocal() as s:
        canonical.apply(s, source, ADAPTERS[source].map(Record(resource, "x", payload)))
        s.commit()


def _evidence(n: int) -> None:
    """The configuration-wipe certificate on file (another gate, P9-10.7's: so that only the inventory gate decides)."""
    key = serial_key(ORG, sn(n))
    row = {"asset_key": key, "type": "config_wipe", "result": "pass", "ref": "W-1", "at": OLD, "value": {}}
    with SessionLocal() as s:
        canonical.apply(s, "manual", [Fact("compliance", compliance_key(key, "config_wipe"), f, v) for f, v in row.items()])
        s.execute(text("DELETE FROM job WHERE kind = 'case.gateRecheck'"))
        s.commit()


def _event(unit: dict[str, Any], reason: str = "decommission", **over: Any) -> dict[str, Any]:
    facts = {"serial": unit["serial"], "model": unit["model"], "site": unit["siteId"], "removed_at": unit["removedAt"],
             "removal_job": unit["jobId"], "programme": unit["programme"]}  # fmt: skip
    return {"org_unit_id": ORG, "template_key": "telecom_network", "asset_key": serial_key(ORG, unit["serial"]),
            "reason": reason, "facts": facts} | over  # fmt: skip


def _open(unit: dict[str, Any], reason: str = "decommission", **over: Any) -> dict:
    return call("case.open", _event(unit, reason, **over), "planner-a")


def _case(cid: str) -> dict[str, Any]:
    with SessionLocal() as s:
        c = cases.get(s, cid)
    assert c is not None
    return c


def _count() -> int:
    with engine.connect() as conn:
        sql = text("SELECT count(*) FROM case_record WHERE data ->> 'template' = 'telecom_network'")
        return int(conn.execute(sql).scalar_one())


def _gate(c: dict[str, Any]) -> dict[str, Any]:
    return next(g for g in c["gates"] if g["id"] == "G-NET-INV")


def _items(cid: str) -> list[dict[str, Any]]:
    with SessionLocal() as s:
        rows = s.execute(
            text(
                "SELECT id, status, owner_role, action, outcome FROM work_item "
                "WHERE case_id = :c AND type = 'EX-TN-INV' ORDER BY id"
            ),
            {"c": cid},
        ).mappings().all()  # fmt: skip
    return [dict(r) for r in rows]


def _recheck() -> None:
    with SessionLocal() as s:
        jobs = s.execute(text("SELECT payload FROM job WHERE kind = 'case.gateRecheck' AND status = 'queued'")).scalars().all()
    for p in jobs:
        worker.HANDLERS["case.gateRecheck"](p)
    with SessionLocal() as s:
        s.execute(text("DELETE FROM job WHERE kind = 'case.gateRecheck'"))
        s.commit()


def test_tn_04_one_case_per_serial():
    units = _job("RJ-01", "SITE-101", [(1, "RRU-4410"), (2, "RRU-4410"), (3, "RAD-7700")])
    for u in units:
        _write("tn_decom", "removal_jobs", u)
    ids = [_ok(_open(u))["case_id"] for u in units]
    assert len(set(ids)) == 3 and _count() == 3
    for cid, u in zip(ids, units, strict=True):
        c = _case(cid)
        assert (c["template"], c["assetId"], c["serial"], c["intake"]["reason"]) == (
            "telecom_network", serial_key(ORG, u["serial"]), u["serial"], "decommission",
        )  # fmt: skip
        facts = {f["fact"]: f for f in c["network"]["facts"]}
        assert facts["site"]["value"] == "SITE-101" and facts["removed_at"]["value"] == u["removedAt"]
        assert facts["removal_job"]["value"] == "RJ-01" and facts["model"]["value"] == u["model"]
        assert all(f["source"] == "tn_decom" and isinstance(f["ageDays"], float) and f["at"] for f in facts.values())
        net = c["network"]
        assert (net["site"], net["removedAt"], net["source"]) == ("SITE-101", u["removedAt"], "tn_decom")
    # the tracker's own write gave the age of the facts it wrote; a second event for the serial joins the open case
    j = _ok(_open(units[0], "manual", source="tn_inv"))
    assert j["case_id"] == ids[0] and _count() == 3
    joined = _case(ids[0])
    assert {f["source"] for f in joined["network"]["facts"]} == {"tn_decom", "tn_inv"}
    assert [x["reason"] for x in joined["intake"]["joined"]] == ["manual"]
    again = _open(units[0], "manual", source="tn_inv")  # a replay of the joined event is refused
    assert again["ok"] is False and "already open" in json.dumps(again)
    replay = _open(units[1])  # so is the same event for the first reason
    assert replay["ok"] is False and "already open" in json.dumps(replay)


def test_tn_04_a_serial_needs_its_facts():
    (u,) = _job("RJ-01", "SITE-101", [(1, "RRU-4410")])
    body = _event(u)
    body["facts"].pop("site")
    r = call("case.open", body, "planner-a")
    assert r["ok"] is False and "site" in json.dumps(r)
    assert _count() == 0


def test_tn_05_unknown_serial_holds_without_valuation():
    (u,) = _job("RJ-09", "SITE-301", [(202, "RAD-7700")])
    _write("tn_decom", "removal_jobs", u)
    _evidence(202)
    c = _case(_ok(_open(u))["case_id"])
    gate = _gate(c)
    assert gate["passed"] is False and gate["hold"] is True and gate["missing"] == ["Network inventory match"]
    assert gate["reason"] == "Serial not in network inventory" and sorted(gate["routes"]) == sorted(ROUTES)
    assert c["gateHold"] is not None and c["recommendation"] is None and c["stage"] == "none"
    assert all(r["excluded"] for r in c["routes"])  # no route is valued
    (item,) = _items(c["id"])
    assert (item["status"], item["owner_role"], item["action"]) == ("open", "Warehouse Manager", ACTION)
    assert forbidden("work.resolve")  # an agent never clears the exception


def test_tn_05_model_or_site_that_differs_holds():
    (u,) = _job("RJ-09", "SITE-301", [(203, "RAD-7700")])
    _write("tn_decom", "removal_jobs", u)
    _evidence(203)
    _write("tn_inv", "elements", _element(203, "RAD-7700", "SITE-999"))
    c = _case(_ok(_open(u))["case_id"])
    assert _gate(c)["passed"] is False and "SITE-999" in _gate(c)["reason"] and "SITE-301" in _gate(c)["reason"]
    assert c["gateHold"] is not None and len(_items(c["id"])) == 1
    _write("tn_inv", "elements", _element(203, "RRU-4410", "SITE-301"))  # the site is right now, the model is not
    _recheck()
    again = _case(c["id"])
    assert _gate(again)["passed"] is False and "RRU-4410" in _gate(again)["reason"] and again["gateHold"] is not None


def test_tn_05_resumes_when_match_exists():
    (u,) = _job("RJ-09", "SITE-301", [(201, "RAD-7700")])
    _write("tn_decom", "removal_jobs", u)
    _evidence(201)
    c = _case(_ok(_open(u))["case_id"])
    assert c["gateHold"] is not None and c["recommendation"] is None
    (item,) = _items(c["id"])
    assert item["status"] == "open"
    # the element appears in the inventory (the next sync): the case resumes on its own
    _write("tn_inv", "elements", _element(201, "RAD-7700", "SITE-301"))
    with SessionLocal() as s:
        sql = text("SELECT dedupe_key FROM job WHERE kind = 'case.gateRecheck' AND status = 'queued'")
        queued = s.execute(sql).scalars().all()
    assert queued == [f"case.gateRecheck:{serial_key(ORG, sn(201))}"]
    _recheck()
    got = _case(c["id"])
    assert _gate(got)["passed"] is True and got["gateHold"] is None
    # no route fails for the inventory any more (the telecom valuer comes with P9-10.8: its routes have no value lines yet)
    assert all("Unit matches network inventory" not in str(r["failReason"]) for r in got["routes"])
    with engine.connect() as conn:
        log = conn.execute(text("SELECT reason, actor FROM case_stage_log WHERE case_id = :c ORDER BY id"), {"c": c["id"]}).all()
    assert log[-1][1] == "system" and log[-1][0].startswith("Released: Network inventory match from tn_inv")
    assert got.get("approval") is None  # released, not approved: a person still decides
    (done,) = _items(c["id"])
    assert done["status"] == "done" and done["outcome"] == "released"


def test_tn_05_a_matching_unit_is_not_held():
    (u,) = _job("RJ-02", "SITE-102", [(4, "RRU-4410")])
    _write("tn_decom", "removal_jobs", u)
    _write("tn_inv", "elements", _element(4, "RRU-4410", "SITE-102"))
    _evidence(4)
    c = _case(_ok(_open(u))["case_id"])
    assert _gate(c)["passed"] is True and c.get("gateHold") is None and _items(c["id"]) == []


def test_tn_04_intake_leaves_other_templates_alone():
    assert intake.UNIT_REASONS == ("decommission",) and "lease_end" in intake.REASONS

"""Plan 9, P9-11.6 (stories MR-04 and MR-05): one case per asset tag and the decontamination gate G-MED-DECON.

A rental return opens a `medical_rental` case keyed by the tag (`tag_key`) with its hospital, depot and check-in time, each
with source and age; a second event for the same tag joins the open case. Without a decontamination record that ENDS after
check-in, every route fails (service included), the device is held, `EX-MR-DECON` goes to the decontamination lead and the
case releases itself, per tag, when a valid record arrives. Facts are written by the real adapters' mapping on literal
records (no source-sim). Legal note: Kinective's Legal team reviews the gate's wording before it is relied on.
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
from di.services.canonical.schema import compliance_key, tag_key
from di.services.canonical.store import Fact
from di.services.cases import store as cases
from di.services.engine.routes import mk_route
from di.services.modeler.gates import apply_gate_results, evaluate_gates
from di.services.modeler.pack import load_pack
from tests import starting
from tests.helpers import call

ORG = "Customer A"
PACK = Path(__file__).resolve().parents[1] / "di" / "services" / "modeler" / "packs" / "medical_rental.json"
REASON = "Decontamination record required"
IN = "2026-11-17T06:00:00+00:00"
AFTER = "2026-11-17T09:30:00+00:00"
BEFORE = "2026-11-17T05:15:00+00:00"


def tag(n: int) -> str:
    return f"SYN-MR-IP-{n:04d}"


def _return(n: int, depot: str = "EAST") -> dict[str, Any]:
    return {
        "returnId": f"RET-{n:04d}", "tag": tag(n), "hospitalId": "HOSP-D", "ward": "Ward 3", "wardType": "general",
        "depot": depot, "checkedInAt": IN, "previousRentalEnd": "2026-11-16", "org_unit_id": ORG,
    }  # fmt: skip


def _cycle(n: int, end: str, **over: Any) -> dict[str, Any]:
    return {
        "cycleId": f"DC-{n:04d}", "tag": tag(n), "method": "standard", "enhanced": False,
        "cycleStartedAt": "2026-11-17T04:00:00+00:00", "cycleEndedAt": end, "operatorRef": "OP-01", "result": "pass",
        "org_unit_id": ORG,
    } | over  # fmt: skip


def _clean() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM job WHERE kind = 'case.gateRecheck'"))
        conn.execute(text("DELETE FROM agent_run_step"))
        conn.execute(text("DELETE FROM agent_run"))
        conn.execute(text("DELETE FROM agent_proposal"))
        conn.execute(text("DELETE FROM pack_version"))
        conn.execute(text("DELETE FROM customer_overlay"))
        conn.execute(text("DELETE FROM provenance WHERE key LIKE :p"), {"p": "%:SYN-MR-%"})
        conn.execute(text("DELETE FROM canonical WHERE key LIKE :p"), {"p": "%:SYN-MR-%"})


def _ok(r: dict) -> dict:
    assert r.get("ok"), r
    return r["output"]


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    _clean()
    doc: dict[str, Any] = copy.deepcopy(json.loads(PACK.read_text(encoding="utf-8")))
    doc["version"] = "1.9.1"
    pid = _ok(call("pack.import", {"doc": doc}, "admin"))["id"]
    _ok(call("pack.submit", {"id": pid}, "admin"))
    _ok(call("pack.approve", {"id": pid}, "approver"))
    with SessionLocal() as s:
        for sid in ("mr_rental", "mr_decon"):
            extra.register(s, sid, ORG)
        s.commit()
    yield
    _clean()
    starting.reset()


def _write(source: str, resource: str, payload: dict[str, Any]) -> None:
    with SessionLocal() as s:
        canonical.apply(s, source, ADAPTERS[source].map(Record(resource, "x", payload)))
        s.commit()


def _open(n: int, **over: Any) -> dict:
    body = {"org_unit_id": ORG, "template_key": "medical_rental", "asset_key": tag_key(ORG, tag(n)), "reason": "rental_return",
            "facts": {"tag": tag(n)}} | over  # fmt: skip
    return call("case.open", body, "planner-a")


def _case(cid: str) -> dict:
    with SessionLocal() as s:
        c = cases.get(s, cid)
    assert c is not None
    return c


def _other_gates(n: int) -> None:
    """The service record, field safety status and refurbishment assessment on file (other gates of the pack, later tasks:
    so that only the decontamination gate decides)."""
    key = tag_key(ORG, tag(n))
    for t in ("service_record", "field_safety_status", "refurb_assessment", "servicing_assessment"):
        row = {"asset_key": key, "type": t, "result": "pass", "ref": "R-1", "at": "2026-11-01T00:00:00+00:00", "value": {}}
        with SessionLocal() as s:
            canonical.apply(s, "manual", [Fact("compliance", compliance_key(key, t), f, v) for f, v in row.items()])
            s.commit()
    with SessionLocal() as s:
        s.execute(text("DELETE FROM job WHERE kind = 'case.gateRecheck'"))
        s.commit()


def _held(n: int, end: str | None = None) -> dict[str, Any]:
    _write("mr_rental", "returns", _return(n))
    _other_gates(n)
    if end:
        _write("mr_decon", "cycles", _cycle(n, end))
    return _case(_ok(_open(n))["case_id"])


def _gate(c: dict, gate_id: str = "G-MED-DECON") -> dict:
    return next(g for g in c["gates"] if g["id"] == gate_id)


def _failed(c: dict) -> dict[str, str]:
    """The reason each route of the pack fails with when the case's gates are applied to it."""
    pack = load_pack("medical_rental")
    routes = [mk_route({"id": r.id, "plan": r.id, "terms": []}) for r in pack.routes]
    apply_gate_results(routes, evaluate_gates(c, pack))
    return {r["id"]: r["failReason"] for r in routes if r["excluded"]}


def _items(cid: str, status: str = "open") -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT type, owner_role, action FROM work_item WHERE case_id = :c AND type = 'EX-MR-DECON' AND status = :s"),
            {"c": cid, "s": status},
        ).mappings()
        return [dict(r) for r in rows]


def _recheck() -> None:
    with SessionLocal() as s:
        jobs = s.execute(text("SELECT payload FROM job WHERE kind = 'case.gateRecheck' AND status = 'queued'")).scalars().all()
    for p in jobs:
        worker.HANDLERS["case.gateRecheck"](p)
    with SessionLocal() as s:
        s.execute(text("DELETE FROM job WHERE kind = 'case.gateRecheck'"))
        s.commit()


def _count() -> int:
    with engine.connect() as conn:
        sql = text("SELECT count(*) FROM case_record WHERE data ->> 'template' = 'medical_rental'")
        return int(conn.execute(sql).scalar_one())


def test_mr_04_one_case_per_tag():
    _write("mr_rental", "returns", _return(1))
    r = _ok(_open(1))
    c = _case(r["case_id"])
    facts = {f["fact"]: f for f in c["rental"]["facts"]}
    assert (c["template"], c["assetId"], c["intake"]["reason"]) == ("medical_rental", tag_key(ORG, tag(1)), "rental_return")
    assert (facts["hospital"]["value"], facts["depot"]["value"], facts["checked_in_at"]["value"]) == ("HOSP-D", "EAST", IN)
    assert all(f["source"] == "mr_rental" and isinstance(f["ageDays"], float) and f["at"] for f in facts.values())
    # a second event for the same tag joins the open case; a replay of it is a duplicate
    again = {"reason": "manual", "facts": {"tag": tag(1), "hospital": "HOSP-E"}, "source": "mr_assets"}
    assert _ok(_open(1, **again))["case_id"] == r["case_id"]
    joined = _case(r["case_id"])
    assert {f["source"] for f in joined["rental"]["facts"]} == {"mr_rental", "mr_assets"}
    assert [j["reason"] for j in joined["intake"]["joined"]] == ["manual"]
    assert _open(1, **again)["error"]["code"] == "duplicate"
    assert _count() == 1
    _write("mr_rental", "returns", _return(2))
    _ok(_open(2))  # another tag is another case
    assert _count() == 2


def test_mr_05_no_record_blocks_every_route():
    c = _held(3)
    g = _gate(c)
    assert not g["passed"] and g["hold"] and REASON in g["reason"]
    assert sorted(g["routes"]) == ["refurbish", "rerent", "retire", "service_rerent"]  # every route, service included
    assert g["missing"] == ["Decontamination record"] and c["recommendation"] is None
    assert all(r["excluded"] for r in c["routes"])
    failed = _failed(c)  # the gate on the routes of the pack: "<gate name>: <reason>" on every one, the service route too
    assert failed == dict.fromkeys(("rerent", "service_rerent", "refurbish", "retire"), f"Decontamination record: {REASON}")
    items = _items(c["id"])
    assert len(items) == 1 and items[0]["owner_role"] == "Warehouse Manager"
    assert items[0]["action"] == "Re-run decontamination; held until the record exists"
    assert c["gateHold"]["gates"] == ["G-MED-DECON"] and c["stage"] == "none"


def test_mr_05_record_before_checkin_fails():
    c = _held(4, BEFORE)
    g = _gate(c)
    assert not g["passed"] and g["hold"] and REASON in g["reason"]
    assert all(r["excluded"] for r in c["routes"])
    assert len(_items(c["id"])) == 1


def test_mr_05_record_after_checkin_passes():
    c = _held(1, AFTER)
    assert _gate(c)["passed"] and c.get("gateHold") is None and _items(c["id"]) == []
    assert _failed(c) == {}  # the gate fails no route


def test_mr_05_batch_released_per_tag():
    ids = {n: _held(n)["id"] for n in range(1, 7)}  # the six East returns, none decontaminated
    assert all(_case(i)["gateHold"] for i in ids.values()) and all(len(_items(i)) == 1 for i in ids.values())
    for n in (1, 2, 3, 4):  # four valid records arrive
        _write("mr_decon", "cycles", _cycle(n, AFTER))
    _write("mr_decon", "cycles", _cycle(5, BEFORE))  # a record that ends before check-in does not release
    _recheck()
    for n in (1, 2, 3, 4):
        c = _case(ids[n])
        assert c["gateHold"] is None and _items(ids[n]) == [] and len(_items(ids[n], "done")) == 1
        with engine.connect() as conn:
            why = conn.execute(
                text("SELECT reason FROM case_stage_log WHERE case_id = :c AND actor = 'system' ORDER BY id DESC LIMIT 1"),
                {"c": ids[n]},
            ).scalar_one()
        assert why.startswith("Released: Decontamination record from mr_decon at 2026-11-17 09:30 UTC")
    for n in (5, 6):
        assert _case(ids[n])["gateHold"] is not None and len(_items(ids[n])) == 1


def test_mr_05_an_agent_never_clears_the_gate():
    assert forbidden("work.resolve")

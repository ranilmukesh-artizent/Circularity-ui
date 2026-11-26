"""Plan 9, P9-10.8 (stories TN-03, TN-07 and TN-08): the export control gate G-NET-EXP and the trade compliance approval.

A unit whose export class is controlled, or not confirmed (a class inferred from the part number counts as missing, and
no one may accept it as the class), is resold only after trade compliance approves it and only to a bid whose end-user
screening is clear: without screening `resell` fails; with it the case carries the approval `AP-TN-EXP` for the Approver
role, showing the bid, the class with its source and the alternative "keep as spares" with its value. The other routes
say "not triggered for reuse". The classification and the approval are a person's: an agent never approves, classifies or
releases, and the code never derives a class. Facts are written by the real adapters' mapping on literal records (no
source-sim). Legal note: the export rules are the pack's data; Kinective's Legal team reviews them before they are relied
on.
"""

from typing import Any

import pytest
from sqlalchemy import text

from di.connectors import extra, mapping_suggest
from di.core.db import SessionLocal, engine
from di.services.agents.forbidden import forbidden
from di.services.canonical import store as canonical
from di.services.cases import export_evidence
from di.services.engine.routes import mk_route, term
from di.services.modeler.gate_checks.network import check_export_control
from di.services.modeler.gates import apply_gate_results, pack_gates
from di.services.modeler.pack import load_pack
from tests.helpers import call
from tests.test_tn_intake import _case, _element, _job, _ok, _open, _write, fresh, sn  # noqa: F401

UNSCREENED = "Destination and end-user screening not on file"
REUSE = "not triggered for reuse"
INFERRED = "asset.export_class"
MODELS = ("RAD-7700", "RRU-4410", "RTR-880")


@pytest.fixture(autouse=True)
def broker(fresh):  # noqa: F811 - after the intake fixture: the broker source and a clean market
    with SessionLocal() as s:
        extra.register(s, "tn_broker", None)
        s.commit()
    _forget()
    yield
    _forget()


def _forget() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM provenance WHERE source_id = 'tn_broker'"))
        conn.execute(text("DELETE FROM canonical WHERE model = 'market' AND key = ANY(:k)"), {"k": list(MODELS)})
        conn.execute(text("DELETE FROM work_item WHERE type = 'AP-TN-EXP'"))


def _bid(bid_id: str, price: int, screening: str | None, country: str = "AE", ref: str | None = "EUS-9001") -> dict[str, Any]:
    return {"bidId": bid_id, "model": "RAD-7700", "qty": 40, "unitPrice": price, "buyerCountry": country,
            "domestic": country == "US", "endUserScreening": {"result": screening, "ref": ref}}  # fmt: skip


def _bids(model: str, *bids: dict[str, Any]) -> None:
    _write("tn_broker", "bids", {"model": model, "bids": [b | {"model": model} for b in bids]})


def _unit(n: int, model: str = "RAD-7700", **element: Any) -> dict[str, Any]:
    """A removed unit the inventory knows, wiped by the bench; returns its job unit."""
    (u,) = _job("RJ-02", f"SITE-{100 + n}", [(n, model)])
    _write("tn_decom", "removal_jobs", u)
    _write("tn_inv", "elements", _element(n, model, u["siteId"], **element))
    from tests.test_tn_intake import _bench

    _write("tn_bench", "results", _bench(n))
    return u


def _gate(c: dict[str, Any]) -> dict[str, Any]:
    return next(g for g in c["gates"] if g["id"] == "G-NET-EXP")


def _items(cid: str | None = None) -> list[dict[str, Any]]:
    sql = "SELECT case_id, kind, status, owner_role, title, cause, action FROM work_item WHERE type = 'AP-TN-EXP'"
    with SessionLocal() as s:
        rows = s.execute(text(sql + (" AND case_id = :c" if cid else "") + " ORDER BY id"), {"c": cid}).mappings().all()
    return [dict(r) for r in rows]


def _record(cls: str | None, inferred: str | None, screening: str | None = "clear") -> dict[str, Any]:
    bid = _bid("BID-X", 1900, screening) | {"endUserScreening": {"result": screening, "ref": "EUS-1"}}
    read = {"export_class": cls, "class_source": "tn_inv" if cls else None, "inferred": inferred,
            "model": "RAD-7700", "bid": export_evidence.bid_view(bid) if screening is not None else None}  # fmt: skip
    return {
        "type": "export_classification",
        "source": "tn_inv",
        "at": "2026-10-01T00:00:00+00:00",
        "result": "pass",
        "value": read,
    }


def _pure(cls: str | None, inferred: str | None, screening: str | None = "clear") -> tuple[Any, dict[str, Any]]:
    """The export gate's result for a case with that evidence, and the routes it was applied to."""
    pack = load_pack("telecom_network")
    gate = next(g for g in pack_gates(pack) if g.id == "G-NET-EXP")
    case = {"id": "RT-9001", "template": "telecom_network", "evidenceRecords": [_record(cls, inferred, screening)]}
    res = check_export_control(case, pack, gate)
    routes = [mk_route({"id": r.id, "plan": r.id, "terms": [term("Sale", 100, "gain")]}) for r in pack.routes]
    apply_gate_results(routes, [res])
    return res, {r["id"]: r for r in routes}


# ---------------------------------------------------------------- TN-03: the class is never guessed
def test_tn_03_export_class_never_guessed():
    assert mapping_suggest.allowed_choices("tn_inv", "exportClassInferred") == ["ask_system_owner", "confirmed_source_field"]
    assert mapping_suggest.allowed_choices("tn_inv_2", "exportClassInferred") == ["ask_system_owner", "confirmed_source_field"]
    assert mapping_suggest.allowed_choices("tn_inv", "hwRevision") is None  # a conversion table is allowed there
    assert mapping_suggest.allowed_choices("tn_inv", "serial") is None

    def decide(decision: str, **kw: object) -> dict:
        body = {"source_id": "tn_inv", "src": "exportClassInferred", "decision": decision, **kw}
        return call("mapping.decide", body, "developer")

    for refused in (
        decide("accepted", target=INFERRED),  # "accept" is refused
        decide("accepted_with_rule", target=INFERRED, rule="upper"),
        decide("not_needed"),
        decide("replaced", target=INFERRED),  # nor is the inferred value moved into the class by another name
    ):
        assert refused["ok"] is False and refused["error"]["code"] == "validation_error", refused
        assert "never accepted" in refused["error"]["message"]
    rows = [{"src": "exportClassInferred", "target": INFERRED}]
    applied = call("mapping.apply", {"source_id": "tn_inv", "rows": rows}, "developer")
    assert applied["ok"] is False and "never accepted" in applied["error"]["message"], applied
    # the confirmed field is the one choice that records: the inferred value stays in its own field
    ok = decide("replaced", target="asset.export_class_inferred")
    assert ok["ok"] is True, ok
    revision = {"source_id": "tn_inv", "src": "hwRevision", "decision": "accepted", "target": "asset.hw_revision"}
    hw = call("mapping.decide", revision, "developer")
    assert hw["ok"] is True, hw
    # the gate treats a unit whose class is only inferred as class missing: RRU-4410 (inferred 5A992, none confirmed)
    res, routes = _pure(None, "5A992")
    assert res.effect.kind == "require_approval" and res.passed is False and res.effect.routes == ("resell",)
    assert "not confirmed" in res.reason and routes["resell"]["excluded"] is False
    _bids("RRU-4410", _bid("BID-4410-OS", 3300, "clear", "VN") | {"model": "RRU-4410"})
    u = _unit(31, "RRU-4410", exportClassInferred="5A992")
    c = _case(_ok(_open(u))["case_id"])
    g = _gate(c)
    assert g["kind"] == "require_approval" and g["passed"] is False and "5A992" in g["reason"]
    (item,) = _items(c["id"])
    assert "not confirmed" in item["cause"] and "5A992" in item["cause"]


# ---------------------------------------------------------------- TN-07
def test_tn_07_resale_of_controlled_needs_trade_compliance():
    res, routes = _pure("5A002", None)
    assert (res.gate_id, res.passed, res.effect.kind, res.effect.routes) == ("G-NET-EXP", False, "require_approval", ("resell",))
    assert res.effect.step == "Trade compliance approval" and res.effect.hold is False
    assert dict(res.route_notes) == {"redeploy": REUSE, "spare": REUSE, "harvest": REUSE, "recycle": REUSE}
    assert routes["resell"]["excluded"] is False  # valued: the approval is the control, not a block
    # a class outside the controlled list, and a unit with no class at all, are not export controlled
    assert _pure("EAR99", None)[0].passed is True and _pure(None, None)[0].passed is True
    _bids("RAD-7700", _bid("BID-7700-OS", 1900, "clear"))
    u = _unit(7, "RAD-7700", exportClassConfirmed="5A002")  # TN-S7: a controlled radio with an overseas bid
    c = _case(_ok(_open(u))["case_id"])
    g = _gate(c)
    assert g["passed"] is False and g["kind"] == "require_approval" and g["routes"] == ["resell"]
    assert g["routeNotes"] == {"redeploy": REUSE, "spare": REUSE, "harvest": REUSE, "recycle": REUSE}
    assert [s["step"] for s in c["requiredSteps"] if s["gate"] == "G-NET-EXP"] == ["Trade compliance approval"]
    assert c.get("gateHold") is None  # not held: a person decides


def test_tn_07_no_screening_blocks_resale():
    res, routes = _pure("5A002", None, "none")
    assert res.passed is False and res.effect.kind == "block" and res.effect.routes == ("resell",) and res.reason == UNSCREENED
    assert routes["resell"]["excluded"] is True and UNSCREENED in routes["resell"]["failReason"]
    assert all(routes[r]["excluded"] is False for r in ("redeploy", "spare", "harvest", "recycle"))
    assert _pure("5A002", None, "refer")[0].reason == UNSCREENED  # anything but clear is not screened
    assert _pure("5A002", None, None)[0].reason == UNSCREENED  # and no bid at all
    _bids("RAD-7700", _bid("BID-7700-OS", 1900, "none", ref=None))
    u = _unit(8, "RAD-7700", exportClassConfirmed="5A002")
    c = _case(_ok(_open(u))["case_id"])
    g = _gate(c)
    assert g["passed"] is False and g["kind"] == "block" and g["reason"] == UNSCREENED and g["routes"] == ["resell"]
    # (the pack has no value lines until the valuer of P9-10.9: the routes are excluded for that reason first)
    assert _items(c["id"]) == []  # nothing to approve until the buyer is screened


def test_tn_07_best_cleared_bid_is_the_one_shown():
    _bids("RAD-7700", _bid("BID-LOW", 1500, "clear", "US"), _bid("BID-HIGH", 2100, "refer"), _bid("BID-MID", 1900, "clear"))
    u = _unit(9, "RAD-7700", exportClassConfirmed="5A002")
    c = _case(_ok(_open(u))["case_id"])
    (item,) = _items(c["id"])
    assert "BID-MID" in item["cause"] and "BID-HIGH" not in item["cause"]  # the best bid that is screened clear


# ---------------------------------------------------------------- TN-08
def test_tn_08_inbox_shows_bid_and_alternative():
    _bids("RAD-7700", _bid("BID-7700-OS", 1900, "clear"))
    ids = []
    for n in range(50, 90):  # 40 RAD-7700 units, class confirmed 5A002 by the inventory
        ids.append(_ok(_open(_unit(n, "RAD-7700", exportClassConfirmed="5A002")))["case_id"])
    items = _items()
    assert len(items) == 40 and sorted(i["case_id"] for i in items) == sorted(ids)
    for i in items:
        assert (i["kind"], i["status"], i["owner_role"]) == ("exception", "open", "Approver")  # My work shows it as approval
        assert "BID-7700-OS" in i["cause"] and "5A002" in i["cause"] and "tn_inv" in i["cause"]
        assert "keep as spares" in i["cause"].lower() and "keep as spares" in i["action"].lower()
        assert i["case_id"] in i["title"]
    from di.core import policy
    from di.core.auth import load_context
    from di.services.actions.pipeline import Actor, CallContext
    from di.services.cases import process

    with SessionLocal() as s:  # the Approver's My work lists the 40 as approvals, with the bid in the cause
        pctx = load_context(s)
        mine = process.items_for(s, CallContext(actor=Actor(account=policy.account("approver", pctx), ctx=pctx), session=s))
    shown = [w for w in mine if w.id.startswith("w:") and w.case_id in ids]
    assert len(shown) == 40 and {w.kind for w in shown} == {"approval"} and all("BID-7700-OS" in (w.cause or "") for w in shown)
    # only a person approves, classifies or releases: an agent's call is refused
    for action in ("decision.approve", "decision.override", "decision.decline"):
        assert forbidden(action), action
    from tests.helpers import client, h

    r = client.post("/api/actions/decision.approve", json={"case_id": ids[0]}, headers=h("approver") | {"X-Agent": "coordinator"})
    assert r.json()["ok"] is False  # whatever the headers say, an agent-prepared approve is refused
    assert forbidden("mapping.answerOwner") and forbidden("work.resolve")
    # a joined replay does not open a second item for a case that has one
    assert len(_items(ids[0])) == 1


def test_tn_08_item_closes_when_the_class_is_confirmed_not_controlled():
    _bids("RAD-7700", _bid("BID-7700-OS", 1900, "clear"))
    u = _unit(91, "RAD-7700", exportClassConfirmed="5A002")
    cid = _ok(_open(u))["case_id"]
    assert [i["status"] for i in _items(cid)] == ["open"]
    # the inventory's owner confirms a class that is not controlled; the case is valued again
    _write("tn_inv", "elements", _element(91, "RAD-7700", u["siteId"], exportClassConfirmed="EAR99"))
    from di.services.cases import intake, store

    with SessionLocal() as s:
        c = canonical_case(s, cid)
        intake.revalue(s, c)
        store.save(s, c)
        s.commit()
    assert _gate(_case(cid))["passed"] is True
    assert [i["status"] for i in _items(cid)] == ["done"]


def canonical_case(s: Any, cid: str) -> dict[str, Any]:
    from di.services.cases import store

    c = store.get(s, cid, for_update=True)
    assert c is not None
    return c


def test_tn_evidence_reads_the_class_with_its_source():
    _bids("RAD-7700", _bid("BID-7700-OS", 1900, "clear"))
    _unit(60, "RAD-7700", exportClassConfirmed="5A002")
    from di.services.canonical.schema import serial_key
    from tests.test_tn_intake import ORG

    with SessionLocal() as s:
        read = export_evidence.read(s, serial_key(ORG, sn(60)), "RAD-7700")
        assert canonical.get(s, "market", "RAD-7700") is not None
    assert read is not None and read["export_class"] == "5A002" and read["class_source"] == "tn_inv"
    assert read["bid"]["id"] == "BID-7700-OS" and read["bid"]["screening"] == "clear" and read["bid"]["ref"] == "EUS-9001"
    (rec,) = export_evidence.evidence(read)
    assert rec["type"] == "export_classification" and rec["source"] == "tn_inv" and rec["value"]["bid"] == read["bid"]
    assert export_evidence.evidence(None) == []

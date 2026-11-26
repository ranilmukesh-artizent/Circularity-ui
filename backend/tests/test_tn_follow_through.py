"""Plan 9, P9-10.16 (stories TN-19, TN-23, TN-24): the telecom pack's follow-through, battery lanes and recycling.

An approved route's steps go to the executing system (`writers_telecom`): redeploy `site_transfer` (tn_inv), spare `refurb_order`
(tn_bench) and `spares_transfer` (tn_inv), resell `broker_listing` (tn_broker), harvest `teardown` (tn_bench), recycle
`recycler_pickup` (tn_recycler); each reply is the confirmation recorded on the instruction. `requisition.reduce` cuts a purchase
requisition a reuse route fills: an agent's call is held and a person accepts it. G-BAT-4 sends lithium units by the
dangerous-goods lane and refuses resale of a damaged one; G-DS-1 refuses a recycler whose certificate expired;
G-WEEE-2 needs category and weight for an EU site. The source clients are stubbed: nothing calls the shared source-sim.
Legal note: the battery transport, recycler certification and WEEE rules rest on research summaries;
Kinective's Legal team reviews them before reliance.
"""

from typing import Any, ClassVar

import pytest
from sqlalchemy import text

from di.connectors.http import SourceError
from di.core.db import SessionLocal
from di.services.agents.forbidden import HELD_FOR_PERSON
from di.services.instructions import writers
from di.services.modeler.gate_checks.battery import check_battery_lane
from di.services.modeler.gate_checks.downstream import check_downstream_vendor, check_weee_record
from di.services.modeler.gates import pack_gates
from di.services.modeler.pack import load_pack
from tests import starting
from tests.helpers import call, client, h
from tests.test_tn_routing import decide, route, sample

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")

PACK = load_pack("telecom_network")
CERTS = {"RV-1": {"scheme": "R2v3", "ref": "R2V3-0001", "expires": "2027-06-30"},
         "RV-2": {"scheme": "e-Stewards", "ref": "ES-0002", "expires": "2026-10-31"}}  # fmt: skip
NOW = "2026-11-26T09:00:00+00:00"


class _Reply:
    def __init__(self, doc: Any):
        self._doc = doc

    def json(self) -> Any:
        return self._doc


class Stub:
    """A source client that records its calls and answers like the mocks."""

    calls: ClassVar[list[tuple[str, str, str, Any]]] = []
    ids: ClassVar[dict[str, str]] = {
        "/transfer-orders": "TO-0001", "/refurb-orders": "RF-0001", "/teardowns": "TD-0001", "/listings": "LS-0001",
        "/pickups": "PU-0001",
    }  # fmt: skip

    def __init__(self, source: str):
        self.source = source

    def request(self, method: str, path: str, json: dict[str, Any] | None = None, headers: dict[str, str] | None = None):
        Stub.calls.append((self.source, method, path, json))
        if path.startswith("/requisitions/"):
            return _Reply({"reqId": path.split("/")[2], "quantity": 1, "status": "open", "reducedBy": (json or {})["qty"]})
        doc = {"orderId": self.ids[path], "teardownId": self.ids[path], "listingId": self.ids[path], "pickupId": self.ids[path]}
        return _Reply(doc)

    def get_json(self, path: str, params: dict[str, Any] | None = None):
        return [{"bidId": "BID-A", "unitPrice": 3400}, {"bidId": "BID-B", "unitPrice": 3250}]

    def close(self) -> None:
        pass


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    Stub.calls = []
    monkeypatch.setattr(writers, "client", lambda s, source_id: Stub(source_id))
    return


def _case(**over: Any) -> dict[str, Any]:
    return {"id": "RT-9001", "template": "telecom_network", "assetId": "Customer A:SN-TN-0001", "network": {"model": "RRU-4410"},
            "chosen": {"dest": {"site": "SITE-N-014", "region": "North"}}} | over  # fmt: skip


def _send(kind: str, c: dict[str, Any]):
    return writers.WRITERS[writers.write_kind(c, kind)](None, {"idem_key": "k"}, c, {})  # type: ignore[arg-type]


def test_tn_19_steps_per_route():
    near = {"demand.open_site_demand": True, "demand.id": "SD-112", "demand.site": "SITE-N-014"}
    d = decide(sample("TN-S1", **near))
    assert route(d, "redeploy")["steps"] == ["site_transfer"]
    assert route(d, "spare")["steps"] == ["refurb_order", "spares_transfer"]
    assert route(d, "resell")["steps"] == ["broker_listing"]
    assert route(d, "harvest")["steps"] == ["teardown"]
    assert route(d, "recycle")["steps"] == ["recycler_pickup"]


def test_tn_19_each_step_is_written_and_its_confirmation_recorded():
    down = {"vendor_id": "RV-1", "weee_category": "IT", "weight_kg": 14, "certificate": CERTS["RV-1"]}
    kinds = ("site_transfer", "spares_transfer", "refurb_order", "teardown", "broker_listing", "recycler_pickup")
    out = {k: _send(k, _case(downstream=down)) for k in kinds}
    assert [(s, p, b) for s, _m, p, b in Stub.calls] == [
        ("tn_inv", "/transfer-orders", {"serial": "SN-TN-0001", "toSite": "SITE-N-014"}),
        ("tn_inv", "/transfer-orders", {"serial": "SN-TN-0001", "toPool": "North"}),
        ("tn_bench", "/refurb-orders", {"serial": "SN-TN-0001", "kind": "refurbish"}),
        ("tn_bench", "/teardowns", {"serial": "SN-TN-0001"}),
        ("tn_broker", "/listings", {"serials": ["SN-TN-0001"], "unitPrice": 3400, "bidId": "BID-A"}),
        ("tn_recycler", "/pickups", {"serials": ["SN-TN-0001"], "vendorId": "RV-1", "weeeCategory": "IT", "weightKg": 14}),
    ]  # fmt: skip
    assert all(o.detail["confirmed"] for o in out.values())
    assert out["site_transfer"].doc_ref == "TO-0001" and out["recycler_pickup"].detail["certificateRef"] == "R2V3-0001"


def test_tn_19_no_destination_or_refusal_is_a_refusal():
    with pytest.raises(writers.Refused):
        _send("site_transfer", _case(chosen={"dest": {}}))

    class Bad(Stub):
        def request(self, *a: Any, **k: Any):
            raise SourceError("client", "certificate_expired", 422)

    writers.client = lambda s, source_id: Bad(source_id)  # type: ignore[assignment]  # monkeypatch restores it
    with pytest.raises(writers.Refused):
        _send("recycler_pickup", _case(downstream={"vendor_id": "RV-2", "weee_category": "IT", "weight_kg": 14}))


def test_tn_24_pickup_without_weight_or_category_is_refused():
    with pytest.raises(writers.Refused, match="WEEE"):
        _send("recycler_pickup", _case(downstream={"vendor_id": "RV-1", "weee_category": "IT"}))
    assert Stub.calls == []


# --- G-BAT-4 ---


def _gate(gid: str):
    return next(g for g in pack_gates(PACK) if g.id == gid)


def test_tn_23_lithium_takes_dg_lane():
    r = check_battery_lane({"battery": {"chemistry": "lithium", "damaged": False}}, PACK, _gate("G-BAT-4"))
    assert r is not None and not r.passed and r.effect.kind == "require_step" and r.effect.step == "dg_lane"
    assert "resell" in r.effect.routes and "recycle" in r.effect.routes
    assert check_battery_lane({"battery": {"chemistry": "lead"}}, PACK, _gate("G-BAT-4")) is None
    assert check_battery_lane({}, PACK, _gate("G-BAT-4")) is None


def test_tn_23_damaged_lithium_cannot_be_resold():
    r = check_battery_lane({"battery": {"chemistry": "lithium", "damaged": True}}, PACK, _gate("G-BAT-4"))
    assert r is not None and r.effect.kind == "block" and r.effect.routes == ("resell",) and r.effect.step == "dg_lane"
    assert dict(r.route_reasons)["resell"] == "Damaged lithium battery: no resale"


# --- G-DS-1 and G-WEEE-2 ---


def _down(vendor: str, **over: Any) -> dict[str, Any]:
    return {"gateNow": NOW, "downstream": {"vendor_id": vendor, "certificate": CERTS[vendor]} | over}


def test_tn_24_recycle_only_qualified_vendor():
    bad = check_downstream_vendor(_down("RV-2"), PACK, _gate("G-DS-1"))
    assert bad is not None and not bad.passed and bad.reason == "Recycler certificate expired 2026-10-31"
    assert bad.effect.routes == ("recycle",)
    ok = check_downstream_vendor(_down("RV-1"), PACK, _gate("G-DS-1"))
    assert ok is not None and ok.passed and "R2V3-0001" in ok.reason  # the certificate reference is kept
    assert check_downstream_vendor({}, PACK, _gate("G-DS-1")) is None


def test_tn_24_eu_pickup_needs_category_and_weight():
    g = _gate("G-WEEE-2")
    miss = check_weee_record(_down("RV-1", site_region="EU", weee_category="IT"), PACK, g)
    assert miss is not None and not miss.passed and miss.reason == "WEEE category and weight required for an EU site"
    full = check_weee_record(_down("RV-1", site_region="EU", weee_category="IT", weight_kg=14), PACK, g)
    assert full is not None and full.passed
    assert check_weee_record(_down("RV-1", site_region="North"), PACK, g) is None  # not an EU site


# --- requisition.reduce ---

AGENT = {"id": "tn-follow", "name": "Follow-through", "tools": ["request_missing_evidence"], "autonomy": "propose"}
BODY = {"case_id": "RT-1048", "req_id": "PR-3302", "qty": 1, "reason": "Unit TN-S1 fills the need"}


@pytest.fixture
def agent():
    starting.reset()
    with SessionLocal() as s:
        s.execute(text("DELETE FROM agent_proposal"))
        s.commit()
    assert call("agent.register", AGENT, "admin")["ok"] is True
    return
    starting.reset()
    with SessionLocal() as s:
        s.execute(text("DELETE FROM agent_proposal"))
        s.commit()


def _prepared(body: dict[str, Any], user: str = "admin") -> dict[str, Any]:
    hdr = h(user) | {"X-Circularity-Preparer": AGENT["id"]}
    return client.post("/api/actions/requisition.reduce", json=body, headers=hdr).json()


def test_tn_19_requisition_reduce_held_for_person(agent):
    r = _prepared(BODY)
    assert r["ok"] is True and set(r["output"]) == {"held", "reasons"}, r
    assert Stub.calls == []  # nothing is written while it is held
    done = call("proposal.accept", {"id": r["output"]["held"]}, "planner-a")
    assert done["ok"] is True, done
    assert Stub.calls == [("tn_spares", "POST", "/requisitions/PR-3302/reduce", {"qty": 1, "reason": BODY["reason"]})]


def test_requisition_reduce_agent_is_held_not_run(agent):
    assert "requisition.reduce" in HELD_FOR_PERSON
    _prepared(BODY)
    assert Stub.calls == []


def test_requisition_reduce_needs_permission(agent):
    r = call("requisition.reduce", BODY, "engineer")
    assert r["ok"] is False and r["error"]["code"] == "out_of_scope", r
    assert Stub.calls == []


def test_requisition_reduce_tenant_boundary(agent):
    r = call("requisition.reduce", BODY, "planner-b")
    assert r["error"]["code"] == "tenant_boundary", r
    assert Stub.calls == []


def test_requisition_reduce_is_a_commit_with_its_title(agent):
    from di.services.actions.registry import ACTIONS

    a = ACTIONS["requisition.reduce"]
    assert (a.title, a.permission, a.risk) == ("Reduce purchase requisition", "manageRequisitions", "act")
    assert call("requisition.reduce", BODY | {"qty": 0}, "planner-a")["error"]["code"] == "validation_error"

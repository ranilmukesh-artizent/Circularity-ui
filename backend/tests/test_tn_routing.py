"""Plan 9, P9-10.10 (stories TN-12 and TN-13): spares before new, every site demand filled once, site swap by model and firmware.

Decided by the one decider (`decide_case`, R19) on the pack's own samples TN-S1 to TN-S8 plus the inputs the mocks serve
(catalogue price, use probability, six-month need, broker bids, weight). The queue is the units given with each decision, as
the Modeler's sample world gives it. Pure: no database, no source-sim, no model (R16: every figure and reason is computed).
Legal note: export and covered-equipment rules are the pack's data; Kinective's Legal team reviews them before reliance.
"""

import copy
import json
from typing import Any

from di.core import clock
from di.services.cases import bench_evidence, unit_plan
from di.services.cases.decide import Decision, decide_case
from di.services.engine.queue import Bid, fill_orders
from di.services.modeler.compile import CompiledRule, FlowVersion
from di.services.modeler.pack import Diversion, Pack, load_pack

PACK = load_pack("telecom_network")
ORDER = ("gates", "valuation", "queue_plan", "rules", "rank")
INPUTS: dict[str, Any] = {  # what the spares planning, the broker and the bench serve for a radio
    "market.new_price": 9800, "demand.use_probability": {"North": 0.55, "South": 0.2}, "demand.need_6m": {"North": 2, "South": 0},
    "market.broker_bids": [{"bidId": "B-1", "unitPrice": 3400, "qty": 1}], "asset.weight_kg": 14,
}  # fmt: skip


def _raw(sid: str) -> dict[str, Any]:
    doc = json.loads(PACK.model_dump_json())
    return next(s for s in doc["replay"]["example"]["samples"] if s["id"] == sid)


def sample(sid: str, serial: str | None = None, **over: Any) -> dict[str, Any]:
    """A sample unit as a case: its facts (flat dotted names) over the planning inputs."""
    s = _raw(sid)
    f = copy.deepcopy(INPUTS) | s["facts"] | over
    network = {"model": f["asset.model"], "site": "SITE-1", "facts": [{"fact": "programme", "value": "reimbursement_programme"}]}
    c = {"id": sid, "template": "telecom_network", "serial": serial or s["serial"], "network": network}
    return c | f | {"evidenceRecords": _evidence(f, serial or s["serial"])}


def _evidence(f: dict[str, Any], serial: str) -> list[dict[str, Any]]:
    """What the gates read: the inventory's match, and the bench's clean wipe (or the failed ones the sample names)."""
    fails = int(f.get("config.wipe_fail_count") or 0)
    wipe = (
        {"status": "failed", "attempts": fails, "scope": [], "verifiedAt": None, "certificate": None}
        if fails
        else {"status": "verified", "attempts": 1, "scope": ["configuration", "credentials", "keys", "logs"],
              "verifiedAt": "2026-10-03T09:00:00Z", "certificate": "WC-0001"}
    )  # fmt: skip
    inv = {"serial": serial, "model": f["asset.model"], "site": "SITE-1", "status": "removed",
           "manufacturer": f.get("asset.manufacturer"), "region": f.get("asset.region")}  # fmt: skip
    match = {"type": "inventory_match", "source": "tn_inv", "at": clock.now().isoformat(), "result": "pass", "value": inv}
    return [*([match] if f.get("inventory.match") is not False else []), *bench_evidence.evidence({"wipe": wipe})]


def nest(c: dict[str, Any]) -> dict[str, Any]:
    """The same case with its dotted facts also as nested records: the gates and diversions read them that way."""
    out = copy.deepcopy(c)
    for k, v in c.items():
        if "." in k:
            group, _, name = k.partition(".")
            out.setdefault(group, {})[name] = copy.deepcopy(v)
    return out


def decide(c: dict[str, Any], queue: list[dict[str, Any]] | None = None, *rules: CompiledRule, pack: Pack = PACK) -> Decision:
    members = [nest(x) for x in queue] if queue is not None else []
    return decide_case(nest(c), pack, FlowVersion(None, 3, tuple(rules)), queue=members)


def route(d: Decision, rid: str) -> dict[str, Any]:
    return next(r for r in d.routes if r["id"] == rid)


def test_tn_12_spare_before_resale():
    c = sample("TN-S2", **{"asset.spares_region": "North"})
    d = decide(c)
    assert d.route == "spare" and d.recommendation is not None and d.recommendation["plan"] == "Refurbish as a spare"
    assert d.recommendation["dest"]["region"] == "North"
    assert route(d, "resell")["excluded"] and "within 6 months" in route(d, "resell")["failReason"]  # North needs the model


def test_tn_12_no_spare_for_a_region_at_its_target():
    c = sample("TN-S2", **{"asset.spares_region": "North"})
    c.pop("spares.region_below_target")
    d = decide(c)
    assert route(d, "spare")["excluded"] and "No region is below its spares target" in route(d, "spare")["failReason"]
    assert d.route != "spare"


def test_tn_12_resell_only_when_no_region_needs():
    c = sample("TN-S3") | {"market.new_price": 4100, "demand.use_probability": {"North": 0.05}, "demand.need_6m": {"North": 0}}
    c["market.broker_bids"] = [{"bidId": "B-9", "unitPrice": 2800, "qty": 1}]
    d = decide(c)
    assert d.route == "resell" and route(d, "spare")["excluded"] and not route(d, "resell")["excluded"]
    assert d.recommendation is not None and d.recommendation["plan"] == "Resell to a broker"


def _both(**first: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    """TN-S1 and TN-S2 both eligible for SD-112 (the second sees the demand too), North a unit short."""
    near = {"demand.open_site_demand": True, "demand.id": "SD-112", "demand.site": "SITE-N-014",
            "spares.region_below_target": "North", "spares.gap": 1}  # fmt: skip
    return sample("TN-S1", "SN-TN-0001", **near | first), sample("TN-S2", "SN-TN-0002", **near)


def test_tn_12_demand_filled_once():
    a, b = _both()
    da, db = decide(a, [a, b]), decide(b, [a, b])
    assert (da.route, route(da, "redeploy")["excluded"]) == ("redeploy", False)
    assert da.recommendation is not None and da.recommendation["dest"]["demand"] == "SD-112"
    assert db.route == "spare" and route(db, "redeploy")["excluded"]  # the other one goes to its next best route
    assert route(db, "redeploy")["failReason"].endswith("Site demand SD-112 filled by SN-TN-0001")
    assert db.recommendation is not None and db.recommendation["dest"]["region"] == "North"
    # the same plan whatever the order of the queue, and whichever case is asked
    assert decide(b, [b, a]).route == "spare" and decide(a, [b, a]).route == "redeploy"


def test_tn_12_a_spares_gap_is_filled_once_too():
    a, b = _both()
    for c in (a, b):
        c["demand.open_site_demand"] = False  # no named demand: both would be spares for North, which lacks one unit
    da, db = decide(a, [a, b]), decide(b, [a, b])
    assert da.route == "spare" and route(db, "spare")["excluded"]
    assert route(db, "spare")["failReason"].endswith("Spares gap North RRU-4410 filled by SN-TN-0001")
    assert db.route != "spare"


def test_tn_12_an_approved_case_keeps_its_demand():
    a, b = _both()
    held = b | {"stage": "approved", "recommendation": {"id": "redeploy"}}  # decided on already: not offered to another
    assert decide(a, [a, held]).route == "spare" and "SN-TN-0002" in route(decide(a, [a, held]), "redeploy")["failReason"]


def test_tn_12_a_gate_blocked_unit_does_not_take_the_demand():
    a, b = _both(**{"config.wipe_fail_count": 2})  # G-NET-CFG blocks the first unit's routes: it cannot fill the demand
    db = decide(b, [a, b])
    assert db.route == "redeploy" and not route(db, "redeploy")["excluded"]


def test_tn_12_demand_for_another_model_is_not_filled():
    a, _ = _both()
    d = decide(a | {"demand.model": "RAD-7700"})
    assert route(d, "redeploy")["excluded"] and "is for the model RAD-7700" in route(d, "redeploy")["failReason"]


def test_tn_13_firmware_match_adds_upgrade_step():
    c = sample("TN-S8") | {"demand.site": "SITE-207", "demand.id": "SD-207"}
    d = decide(c)
    assert d.route == "redeploy" and d.recommendation is not None
    assert d.recommendation["dest"]["site"] == "SITE-207"
    assert d.recommendation["dest"]["steps"] == ["firmware_upgrade", "site_transfer"]
    current = sample("TN-S1") | {"demand.firmware_min_major": 9}  # firmware 9.1 meets a minimum of 9
    assert decide(current).recommendation["dest"]["steps"] == ["site_transfer"]  # type: ignore[index]


def test_tn_13_model_and_firmware_decide_the_order_of_steps_not_who_wins():
    c = sample("TN-S8") | {"demand.id": "SD-207", "demand.model": "RTR-880"}
    assert decide(c).route == "redeploy"  # the model matches the demand's


def test_fill_orders_is_deterministic_and_fills_each_order_once():
    bids = [Bid("B", "redeploy", "SD-1", 10.0), Bid("A", "redeploy", "SD-1", 10.0), Bid("A", "spare", "G", 3.0)]
    placed, lost = fill_orders(bids, {"G": 1})
    assert placed["A"].order == "SD-1" and "B" not in placed and lost[("B", "redeploy")] == "A"
    assert fill_orders(list(reversed(bids)), {"G": 1}) == (placed, lost)
    assert fill_orders([Bid("A", "spare", "G", 3.0)], {"G": 0})[1] == {("A", "spare"): ""}


def test_order_invariant_telecom_network():
    base = json.loads(PACK.model_dump_json())["customer_layer"]["sample_diversions"]
    fw = next(d["op"] for d in base if d["op"]["id"] == "DV-TN-FW")
    doc = json.loads(PACK.model_dump_json())
    doc["diversions"] = [Diversion(op_id=fw["id"], stage=fw["stage"], when=fw["when"], kind="step", step=fw["step"],
                                   owner_role=fw["owner_role"]).model_dump()]  # fmt: skip
    pack = Pack.model_validate(doc)  # DV-TN-FW enabled
    prefer = CompiledRule("R-1", {}, "prefer", "resell", "prefer resale")
    c = sample("TN-S5")  # RRU-4410, wipe failed twice, firmware current
    c["asset.firmware_major_gap"] = 1  # the diversion matches
    d = decide(c, None, prefer, pack=pack)
    assert d.trace == ORDER  # gates, valuation, queue plan, rules (diversions, business), rank
    failed = [g.gate_id for g in d.gates if not g.passed]
    assert "G-NET-CFG" in failed and d.hold is not None  # the gate speaks first and holds last
    assert route(d, "resell")["excluded"] and d.preferred is None and d.route != "resell"  # no rule revives resale
    assert [s["step"] for s in d.required_steps] == ["destroy_storage", "Firmware upgrade"]  # the gate's, then the diversion's
    s6 = decide(sample("TN-S6"), None, prefer, CompiledRule("R-2", {}, "require", "redeploy", "redeploy"), pack=pack)
    assert all(route(s6, k)["excluded"] for k in ("redeploy", "spare", "resell", "harvest"))  # dispose-only, whatever the rules
    assert s6.route == "recycle" or s6.route is None


def test_paths_agree_telecom_network():
    """TN-S1 to TN-S8: the decider on the sample alone, in the queue of all eight (either order), and a facts mapping nested
    like the valuer snapshot give one route and one net, to the cent."""
    units = {sid: sample(sid, f"SN-TN-{n:04d}") for n, sid in enumerate((f"TN-S{i}" for i in range(1, 9)), 1)}
    queue = list(units.values())
    for sid, c in units.items():
        alone = decide(c, [])
        a, b = decide(c, queue), decide(c, list(reversed(queue)))
        own = ("id", "template", "serial", "network", "evidenceRecords")
        nested = {k: c[k] for k in own} | {"valuer": {k: v for k, v in c.items() if k not in own}}
        n = decide_case(nest(nested), PACK, FlowVersion(None, 3, ()), queue=[])
        assert (a.route, a.net) == (b.route, b.net) == (n.route, n.net), sid
        assert (alone.route, alone.net) == (a.route, a.net), sid  # no two samples name the same demand
    assert decide(units["TN-S1"], queue).route == "redeploy" and decide(units["TN-S8"], queue).route == "redeploy"
    assert unit_plan.key_of(units["TN-S1"], unit_plan.facts_of(units["TN-S1"])) == "SN-TN-0001"

"""Plan 9, P9-11.9 (stories MR-09 and MR-10; R19 and R20 for the medical rental pack): real cases of the pack decided by every
path, and the repair approval a person gives.

`MR-S1` ... `MR-S8` are opened from data (the real adapters' mapping on literal records, no source-sim), valued again, listed in
the Modeler's queue, replayed and decided by `decide_case`: the same route and the same net, to the cent (R19). A case's
requests carry their distance and hospital from the rental system, so the transport is priced; the gates on `rerent` reach
the `rerent:<request>` routes of a real case; and the order of a decision is gates, compliance guardrails, rules and
diversions, valuation, hold (R20): nothing revives a route the decontamination gate blocked. An agent never approves a repair.
Legal note: the wording of the gates needs review by Kinective's Legal team before it is relied on.
"""

import copy
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from di.connectors import extra
from di.connectors.base import Record
from di.connectors.registry import ADAPTERS
from di.core import clock, policy
from di.core.auth import load_context
from di.core.db import SessionLocal, engine
from di.repositories.flows import FlowRow
from di.repositories.live_rules import flow_version, live_pack
from di.services.actions.modeler_sim import template_decider
from di.services.actions.pipeline import Actor, CallContext
from di.services.agents.forbidden import FORBIDDEN_ACTIONS
from di.services.canonical import store as canonical
from di.services.canonical.schema import compliance_key, tag_key
from di.services.canonical.store import Fact
from di.services.cases import intake
from di.services.cases import store as cases
from di.services.cases.decide import decide_case
from di.services.modeler.compile import CompiledRule, FlowVersion
from di.services.modeler.pack import Diversion
from tests import flowkit, starting
from tests.helpers import call, client, h

ORG = "Customer A"
PACK = Path(__file__).resolve().parents[1] / "di" / "services" / "modeler" / "packs" / "medical_rental.json"
IN = "2026-11-17T06:00:00+00:00"
AFTER = "2026-11-17T09:30:00+00:00"
BEFORE_CHECK_IN = "2026-11-17T05:00:00+00:00"
NOTICE = {"noticeId": "FSN-031", "model": "IP-300", "serialFrom": 3000, "serialTo": 3099, "status": "open",
          "correctionRef": "FSN-031-A"}  # fmt: skip
CERT_TEXT = "Certification ends 2026-12-07, before the rental ends 2026-12-27"
CLASSES = {"infusion_pump": "IP", "patient_monitor": "PM", "electric_bed": "EB"}


def tag(n: int) -> str:
    return f"SYN-MR-IP-{n:04d}"


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
    flowkit.reset_flows()
    _clean()
    doc: dict[str, Any] = copy.deepcopy(json.loads(PACK.read_text(encoding="utf-8")))
    doc["version"] = "1.9.3"
    pid = _ok(call("pack.import", {"doc": doc}, "admin"))["id"]
    _ok(call("pack.submit", {"id": pid}, "admin"))
    _ok(call("pack.approve", {"id": pid}, "approver"))
    with SessionLocal() as s:
        for sid in ("mr_rental", "mr_decon", "mr_biomed", "mr_assets"):
            extra.register(s, sid, ORG)
        s.commit()
    yield
    _clean()
    flowkit.reset_flows()
    starting.reset()


def _write(source: str, resource: str, payload: dict[str, Any]) -> None:
    with SessionLocal() as s:
        canonical.apply(s, source, ADAPTERS[source].map(Record(resource, "x", payload)))
        s.commit()


def _manual(n: int, kind: str, result: str = "pass", at: str = "2026-11-01T00:00:00+00:00", **value: Any) -> None:
    key = tag_key(ORG, tag(n))
    row = {"asset_key": key, "type": kind, "result": result, "ref": "R-1", "at": at, "value": value}
    with SessionLocal() as s:
        canonical.apply(s, "manual", [Fact("compliance", compliance_key(key, kind), f, v) for f, v in row.items()])
        s.commit()


def _requests(cls: str) -> list[dict[str, Any]]:
    return [
        {"reqId": f"REQ-{k}", "hospitalId": "HOSP-B", "deviceClass": cls, "startDate": "2026-11-27", "days": 30,
         "region": "EAST", "requestedAt": "2026-11-26T08:00:00+00:00", "latitude": 40.0, "longitude": -74.9}
        for k in (1, 2, 3, 4)
    ]  # fmt: skip


def _get(cid: str) -> dict:
    with SessionLocal() as s:
        c = cases.get(s, cid)
    assert c is not None
    return c


def _open(n: int, *, cls: str = "infusion_pump", decon: str | None = AFTER, model: str = "IP-200", notice: Any = None,
          cert: str = "2027-03-31", facts: dict[str, Any] | None = None) -> dict:  # fmt: skip
    """A return of device n with its records on file (`decon`: when its decontamination cycle ended, None: no record), and its
    case, opened from data with the device facts the valuer reads."""
    _write("mr_assets", "devices", {"tag": tag(n), "deviceClass": cls, "model": model, "serial": 2000 + n, "org_unit_id": ORG})
    _write("mr_biomed", "service", {
        "tag": tag(n), "model": model, "serialNo": 3030 if notice else 2000 + n, "pmDue": "2027-02-15", "pmCode": "PM-12M",
        "lastPm": "2026-02-15", "certificationExpiry": cert, "functionalTest": {"result": "pass", "at": "2026-11-10"},
        "electricalSafety": {"standard": "IEC 62353", "result": "pass", "at": "2026-11-10"}, "notes": [], "repairEstimate": 0,
        "faults": [], "notice": notice, "org_unit_id": ORG,
    })  # fmt: skip
    _write("mr_rental", "returns", {
        "returnId": f"RET-{n:04d}", "tag": tag(n), "hospitalId": "HOSP-D", "ward": "Ward 3", "wardType": "general",
        "depot": "EAST", "checkedInAt": IN, "previousRentalEnd": "2026-11-16", "org_unit_id": ORG,
    })  # fmt: skip
    _write("mr_rental", "demand", {
        "tag": tag(n), "depot": {"latitude": 40.0, "longitude": -75.0}, "requests": _requests(cls), "forecast": [],
        "org_unit_id": ORG,
    })  # fmt: skip
    if decon is not None:
        _write("mr_decon", "cycles", {
            "cycleId": f"DC-{n:04d}", "tag": tag(n), "method": "standard", "enhanced": False,
            "cycleStartedAt": "2026-11-17T04:00:00+00:00", "cycleEndedAt": decon, "operatorRef": "OP-01", "result": "pass",
            "org_unit_id": ORG,
        })  # fmt: skip
    _manual(n, "refurb_assessment")
    body = {"org_unit_id": ORG, "template_key": "medical_rental", "asset_key": tag_key(ORG, tag(n)), "reason": "rental_return",
            "facts": {"tag": tag(n)} | (facts or {})}  # fmt: skip
    return _get(_ok(call("case.open", body, "planner-a"))["case_id"])


def _facts(cls: str = "infusion_pump", age: int = 3, book: int = 1150, sale: int = 1100, repair: int | None = None) -> dict:
    out: dict[str, Any] = {"cls": cls, "age_years": age, "book_value": book, "residual_sale_value": sale}
    return out | ({"repair_estimate": repair} if repair is not None else {})


SCENARIOS: dict[str, dict[str, Any]] = {
    "MR-S1": {"facts": _facts()},
    "MR-S2": {"cert": "2026-12-07", "facts": _facts()},
    "MR-S3": {"decon": None, "facts": _facts()},
    "MR-S4": {"decon": BEFORE_CHECK_IN, "facts": _facts()},
    "MR-S5": {"cls": "patient_monitor", "facts": _facts("patient_monitor", 4, 600, 900, 1350)},
    "MR-S6": {"model": "IP-300", "notice": NOTICE, "facts": _facts()},
    "MR-S7": {"cls": "electric_bed", "facts": _facts("electric_bed", 7, 800, 500)},
    "MR-S8": {"cls": "patient_monitor", "facts": _facts("patient_monitor", 4, 700, 300, 1200)},
}


def _simulated(c: dict[str, Any]) -> tuple[str | None, float]:
    """The route and net the Modeler's simulation decides the case with: its template decider (`modeler_sim.template_decider`)
    under the published rules. The Modeler screen and queue list the three original templates, and this pack has no flow row,
    so the decider is given a flow of the pack's key."""
    f = FlowRow(0, "medical_rental", ORG, "Rental device returns", "pub", 1, None, None, None, None, {}, clock.now())
    with SessionLocal() as s:
        pctx = load_context(s)
        ctx = CallContext(actor=Actor(account=policy.account("planner-a", pctx), ctx=pctx), session=s)
        d = template_decider(ctx, f)(c, ())
    return d.best, d.net


def _replayed(c: dict[str, Any], pack, fv) -> tuple[str | None, float]:
    """The route and net a replay of the case's facts gets from the one decider (P9-7.2, R19)."""
    from di.repositories.replay import Batch
    from di.services.replay import run as replay_run

    when = max(
        clock.now(), datetime(2026, 12, 1, tzinfo=UTC)
    )  # after every record the scenarios write: a replay reads only the past
    known = {**(c.get("valuer") or {})} | {
        k: c[k] for k in ("rentalRequests", "serviceRead", "serviceCheck", "evidenceRecords") if k in c
    }
    facts = {k: {"value": v, "at": when - timedelta(days=1)} for k, v in known.items()}
    it = {"item_id": f"T-PA-{c['id']}", "decided_at": when, "cls": None, "market": None, "actual_route": "retire",
          "realised_value": 1.0, "facts": facts}  # fmt: skip
    got: list = []

    def decide(*a, **k):
        got.append(decide_case(*a, **k))
        return got[-1]

    replay_run.replay(Batch(1, c["template"], ORG, 1, 0, None, {}), [it], fv, pack=pack, decide=decide)
    return got[0].route, got[0].net


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_paths_agree_medical_rental(scenario: str):
    """Intake, re-evaluation, the Modeler's queue, replay and `decide_case` give one route and one net for MR-S1 ... MR-S8."""
    c = _open(int(scenario[-1]), **SCENARIOS[scenario])
    seen = {"opened": (c["recommendation"]["id"] if c.get("recommendation") else None,
                       c["recommendation"]["net"] if c.get("recommendation") else 0.0)}  # fmt: skip
    with SessionLocal() as s:
        c2 = cases.get(s, c["id"], for_update=True)
        assert c2 is not None
        intake.revalue(s, c2)
        cases.save(s, c2)
        s.commit()
    c2 = _get(c["id"])
    seen["reevaluated"] = (c2["recommendation"]["id"] if c2.get("recommendation") else None,
                           c2["recommendation"]["net"] if c2.get("recommendation") else 0.0)  # fmt: skip
    seen["simulation"] = _simulated(c2)
    with SessionLocal() as s:
        pack, fv = live_pack(s, c2), flow_version(s, c2)
        d = decide_case(c["id"], pack, fv, session=s)
        seen["decide_case"] = (d.route, d.net)
        seen["replay"] = _replayed(c2, pack, fv)
    assert len({p[0] for p in seen.values()}) == 1, seen
    nets = [p[1] for p in seen.values()]
    assert max(nets) - min(nets) < 0.005, seen
    held = scenario in ("MR-S3", "MR-S4", "MR-S6")  # no decontamination record, one that ended before check-in, a notice
    assert (seen["opened"][0] is None) is held, (scenario, seen)


def test_mr_09_the_cases_requests_carry_distance_and_hospital():
    """Gap of P9-11.8: the case's `rentalRequests` kept neither the distance nor the hospital, so every request was valued at
    0 miles. Five miles from the depot, 1.40 a mile: 18 x 30 - 7.00 - 35 = 498.00."""
    c = _open(1, **SCENARIOS["MR-S1"])
    reqs = c["rentalRequests"]
    assert [q["req_id"] for q in reqs] == ["REQ-1", "REQ-2", "REQ-3", "REQ-4"]
    assert all(q["distance_miles"] == 5 and q["hospital"] == "HOSP-B" and q["hospital_id"] == "HOSP-B" for q in reqs)
    assert reqs[0]["requested_at"] == "2026-11-26T08:00:00+00:00" and reqs[0]["ends"] == "2026-12-27"
    assert c["recommendation"]["id"] == "rerent:REQ-1" and round(c["recommendation"]["net"], 2) == 498.00
    first = next(r for r in c["routes"] if r["id"] == "rerent:REQ-1")
    assert first["dest"]["distance"] == 5 and first["dest"]["name"] == "Re-rent · HOSP-B"


def test_mr_09_a_gate_on_rerent_reaches_the_request_routes_of_a_real_case():
    """MR-S2: certification ends before every rental ends; G-MED-SVC names `rerent` and `service_rerent`, the case's routes are
    `rerent:<request>`: each fails with the gate's reason, and the case is decided on what is left."""
    c = _open(2, **SCENARIOS["MR-S2"])
    rerents = [r for r in c["routes"] if r["id"].startswith("rerent:")]
    assert len(rerents) == 4
    assert all(r["excluded"] and CERT_TEXT in r["failReason"] for r in rerents)
    assert next(r for r in c["routes"] if r["id"] == "service_rerent")["excluded"]
    assert c["recommendation"]["id"] == "retire"


def test_mr_09_a_business_rule_on_rerent_reaches_the_request_routes_of_a_real_case():
    c = _open(1, **SCENARIOS["MR-S1"])
    with SessionLocal() as s:
        rule = CompiledRule("BR-1", {}, "exclude", "rerent", "no re-rent")
        d = decide_case(c["id"], live_pack(s, c), FlowVersion(None, 3, (rule,)), session=s)
    assert all(r["excluded"] for r in d.routes if r["id"].startswith("rerent:"))
    assert d.route in ("service_rerent", "refurbish", "retire") and d.rules_applied == ["BR-1"]


def test_order_invariant_medical_rental():
    """R20 with MR-S3: no decontamination record. The rule "prefer re-rent", DV-MR-SAME (shortcut to `rerent`) and DV-MR-ISO
    (enhanced decontamination step) revive nothing: every route the decontamination gate blocked stays blocked, and the
    case is held with no recommendation."""
    c = _open(3, **SCENARIOS["MR-S3"])
    assert c["gateHold"]["gates"] == ["G-MED-DECON"] and c["recommendation"] is None
    same = Diversion(op_id="DV-MR-SAME", stage="decide", kind="shortcut", to="rerent",
                     when=[{"fact": "demand.same_hospital_within_24h", "op": "eq", "value": True}])  # fmt: skip
    iso = Diversion(op_id="DV-MR-ISO", stage="match", kind="step", step="enhanced_decon", owner_role="decontamination_lead",
                    when=[{"fact": "asset.ward_type", "op": "eq", "value": "isolation"}])  # fmt: skip
    with SessionLocal() as s:
        pack = live_pack(s, c).model_copy(update={"diversions": [iso, same]})
        probe = {**c, "asset": {"ward_type": "isolation"}, "demand": {"same_hospital_within_24h": True}}
        d = decide_case(probe, pack, FlowVersion(None, 3, (CompiledRule("BR-3", {}, "prefer", "rerent", "prefer re-rent"),)),
                        session=s)  # fmt: skip
    assert d.trace == ("gates", "valuation", "queue_plan", "rules", "rank")
    assert d.diversions == ["DV-MR-ISO", "DV-MR-SAME"]  # both matched, after the gates
    assert d.recommendation is None and d.route is None and d.hold is not None
    why = [(r["id"], r["excluded"], r["failReason"]) for r in d.routes]
    assert all(r["excluded"] for r in d.routes), why  # the 3-year-old pump's refurbish was never considered: still excluded
    gated = [r for r in d.routes if r["id"] != "refurbish"]
    assert gated and all("Decontamination record required" in r["failReason"] for r in gated), why


def test_mr_10_the_case_carries_the_approval_for_the_fleet_manager():
    c = _open(5, **SCENARIOS["MR-S5"])
    holds = c["approvalHolds"]
    assert [x["id"] for x in holds] == ["AP-MR-REPAIR"] and holds[0]["owner"] == "fleet_manager"
    assert holds[0]["income"] == 1512.00 and holds[0]["alternative"]["route"] == "retire"
    assert (
        holds[0]["repairEstimate"] == 1350.0
        and c["recommendation"] is not None
        and holds[0]["route"] == c["recommendation"]["id"]
    )
    ok = _open(1, **SCENARIOS["MR-S1"])
    assert "approvalHolds" not in ok  # no estimate: nothing held


def test_mr_10_an_agent_cannot_approve_the_repair():
    """Approving a repair above the limit is a person's: `decision.approve` is on the forbidden list, whatever the headers say."""
    assert "decision.approve".startswith(FORBIDDEN_ACTIONS)
    c = _open(5, **SCENARIOS["MR-S5"])
    body = {"case_id": c["id"], "rationale": "Repair and re-rent as recommended.", "reviewed": True}
    hdr = h("approver") | {"X-Circularity-Preparer": "coordinator"}
    r = client.post("/api/actions/decision.approve", json=body, headers=hdr)
    assert r.status_code == 403 and r.json()["error"]["code"] == "approval_required", r.json()
    after = _get(c["id"])
    assert after["approval"] is None and after["stage"] == c["stage"]
    assert [x["id"] for x in after["approvalHolds"]] == ["AP-MR-REPAIR"]

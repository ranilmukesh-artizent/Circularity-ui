"""P9-2.22 (R20, phase 1 review finding 2): `decide_case` runs the gates and the hold first, then values the tool fleet
and plans its queue over the routes the gates left eligible. A route a gate blocks never wins a named order, so the order
is not left unfilled by a route that cannot take it. The tool-fleet tests are pure (the cases are given as facts); the
industrial one decides the stored demo cases."""

from datetime import UTC, datetime

from di.core.db import SessionLocal
from di.services.cases import intake, store
from di.services.cases.decide import decide_case
from di.services.modeler.compile import FlowVersion
from di.services.modeler.pack import load_pack

AS_OF = datetime(2026, 10, 2, tzinfo=UTC)
CLAUSE = {"contract_id": "LS-5412", "clause": "7.2", "text": "No loaner pool use without consent", "restricts": ["reuse"]}
RECORD = {
    "type": "contract_clause",
    "source": "lease-system",
    "at": "2026-10-01T08:00:00+00:00",
    "result": "pass",
    "value": CLAUSE,
}
POOL_ORDER = {"kind": "proj", "id": "TPR-1", "who": "Atlanta tool pool", "site": "Atlanta", "need": 20, "rental": 1500,
              "quote": "PR-1", "what": "Tool pool request TPR-1", "when": "raised 29 Oct"}  # fmt: skip
FACTS = {"cls": "CRH", "grade": "C", "rul": 60, "site": "Atlanta", "dem": {"proj": POOL_ORDER}}


def _case(gated: bool) -> dict:
    c = intake.tool_fleet_case("RT-9022", FACTS)
    if gated:
        c["evidenceRecords"] = [RECORD]
    return c


def _decide(case: dict, queue: list | None = None):
    return decide_case(case, load_pack("tool_fleet"), FlowVersion(None, 1, ()), AS_OF, queue=queue)


def test_gate_blocked_route_never_wins_an_order():
    open_ = _decide(_case(False), [])
    assert open_.route == "redeploy" and open_.plan is not None and open_.plan["holds"] == "TPR-1"  # the order is this case's

    gated = _decide(_case(True), [])  # the clause blocks the routes of class reuse (redeploy) until consent is on file
    redeploy = next(r for r in gated.routes if r["id"] == "redeploy")
    assert redeploy["excluded"] and redeploy["failReason"].startswith("Contract entitlement: ")
    assert gated.plan is not None and gated.plan["holds"] is None and gated.plan["lost"] == []
    assert gated.route != "redeploy"

    rival = intake.tool_fleet_case("RT-9023", FACTS | {"grade": "A", "rul": 75})
    other = _decide(_case(True), [rival])  # the next eligible return: this case plans nothing for it
    assert other.plan is not None and other.plan["holds"] is None and other.route != "redeploy"


def test_gate_order_in_trace():
    d = _decide(_case(True), [])
    assert d.trace == ("gates", "valuation", "queue_plan", "rules", "rank")
    assert [g.gate_id for g in d.gates] == ["G-CON-1", "G-CON-2"]  # the contract right passes on the sample line (P9-3.6)


def test_industrial_decide_unchanged():
    """RT-1048 and a book case decide as their stored recommendation says (no gate applies, no queue plan)."""
    with SessionLocal() as s:
        for cid in ("RT-1048", "RT-1051"):
            c = store.get(s, cid)
            assert c is not None
            d = decide_case(cid, load_pack("industrial"), FlowVersion(None, 1, ()), session=s)
            assert d.plan is None and d.gates == [] and d.hold is None
            assert d.route == (c["recommendation"] or {}).get("id")
            if cid == "RT-1048":
                assert d.net == 8314.0  # the hero case's net, as before the change

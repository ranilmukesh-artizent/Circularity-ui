"""B13: the execution actions (adapter.acknowledge, instruction.resend, outcome.confirm) give the demo's results
(fixtures/golden/writes.json, exec_* scenarios, and the RT-1048 journey in actions.json).

People call over HTTP, as in the decision tests. Calls the dump made `as: "system"` are the enterprise-system adapter
(the demo's AF_SYS, `via: 'system'`); no HTTP caller can act as it, so those go through the pipeline with
`pipeline.SYSTEM`, committed or rolled back as the action endpoint does.
"""

import pytest
from test_writes_decisions import Replay, fresh  # noqa: F401  (fresh is a fixture)

from di.core import golden, state
from di.core.db import SessionLocal
from di.services.actions.pipeline import SYSTEM, CallContext, invoke
from di.services.cases import store
from di.services.execution import ex_delivered
from tests.helpers import call, strict

WRITES = golden.load("writes")
JOURNEY = golden.load("actions")["steps"]
SCENARIOS = ["exec_redeploy", "exec_override_resale", "exec_other_routes", "exec_seeded"]


def system_call(action: str, body: dict) -> dict:
    with SessionLocal() as s:
        r = invoke(action, body, CallContext(actor=SYSTEM, session=s))
        s.commit() if r["ok"] else s.rollback()
    return r


def any_call(action: str, body: dict, user: str) -> dict:
    return system_call(action, body) if user == "system" else call(action, body, user)


class ExecReplay(Replay):
    """Replay, with the enterprise-system adapter's calls made as the system actor."""

    def check(self, step: dict, where: str) -> None:
        exp = dict(step["result"])
        got = any_call(step["action"], self.input(step["input"]), step["as"])
        if exp.get("ok") and "seq" in exp:
            assert "seq" in got, (where, got)
            if self.base is None:
                self.base = (exp["seq"], got["seq"])
            exp["seq"] = exp["seq"] - self.base[0] + self.base[1]
        assert strict(got) == strict(exp), where


@pytest.mark.parametrize("name", SCENARIOS)
def test_scenario(fresh, name):  # noqa: F811
    sc, r = WRITES[name], ExecReplay()
    for k, step in enumerate(sc["calls"]):
        r.check(step, f"{name} call {k}: {step['as']} {step['action']} {step['input']}")
    for k, step in enumerate(sc["observed"]):
        got = call(step["action"], step["input"], step["as"])
        assert strict(got) == strict(step["result"]), f"{name} read {k}: {step['as']} {step['action']} {step['input']}"


def _resolve(root, v):
    """Follow the dump's {$ref: "$.steps[5].case_after.exec"} back-references (the demo mutates one object in place,
    so the first occurrence holds its final state)."""
    if isinstance(v, dict) and set(v) == {"$ref"}:
        node = root
        for part in v["$ref"][2:].replace("[", ".").replace("]", "").split("."):
            node = node[int(part)] if part.isdigit() else node[part]
        return node
    return v


def _case(case_id: str) -> dict:
    with SessionLocal() as s:
        return store.get(s, case_id)


def test_journey(fresh):  # noqa: F811
    """The whole RT-1048 journey: every result, the stage after each step, and the approval, plan and outcome the case
    ends with. The dump keeps one object per approval, plan and outcome, mutated in place, so their stored form is
    their final state; only the stage is recorded per step."""
    root, r = {"steps": JOURNEY}, ExecReplay()
    for k, step in enumerate(JOURNEY):
        r.check(step, f"journey step {k}: {step['as']} {step['action']}")
        assert _case("RT-1048")["stage"] == step["case_after"]["stage"], f"stage after step {k}"
    final, c = JOURNEY[-1]["case_after"], _case("RT-1048")
    for f in ("approval", "exec", "outcome"):
        assert strict(c.get(f)) == strict(_resolve(root, final[f])), f


# The demo's answers below come from a fresh demo running the exec_redeploy calls (the dump script's sandbox): no golden
# read returns the event log, and no golden read looks at the case between the last acknowledgement and Finance's
# confirmation, which is when stage 9 carries the delivery sentence (exDelivered).
DELIVERED = (
    "delivered to Chennai Foundry (Site 3) for Customer A against SO-48102 line 10, WH-PNQ-01 → RC-HSR-01 → WH-MAA-02 → "
    "LOC-CHN-03, ETD 08 Oct 08:00, ETA 13 Oct 08:36 (4 days before the need-by date)"
)
EVENTS = [  # newest first, as the demo's EVENTS
    ("outcome.confirmed", "Actual $9,230 against predicted $9,600 on SO-48102; 3 cost lines to the models"),
    ("outcome.reported", "Finance document FI-47401 returned by ERP: actual parts, labour, machine and freight costs posted "
     "against the decision; " + DELIVERED),
    ("delivery.confirmed", "Fulfilment FUL-47375 returned by OMS: proof of delivery signed; " + DELIVERED),
    ("movement.confirmed", "Transfer TR-47362 returned by WMS: picked, staged and shipped against the load"),
    ("load.booked", "Load LD-47388 returned by TMS: load tendered to and accepted by the carrier"),
    ("workorder.created", "Work order WO-47349 returned by MRO: repaired, tested and certified; QMS record updated"),
    ("order.allocated", "Sales order SO-48102 returned by OMS: unit allocated to the order line; planned purchase cancelled "
     "in SAP Ariba"),
    ("instruction.sent", "Repeated message ignored: same idempotency key, no second reservation or work order"),
    ("instruction.sent", ""),
    ("decision.submitted", "Submitted for review by Planner · Customer A"),
]  # fmt: skip


def test_acknowledgement_events(fresh):  # noqa: F811
    for step in WRITES["exec_redeploy"]["calls"]:
        any_call(step["action"], step["input"], step["as"])
    with SessionLocal() as s:
        ev = [(e["type"], e["note"]) for e in state.items(s, "events", newest_first=True) if e["caseId"] == "RT-1048"]
    assert ev == EVENTS
    assert ex_delivered(_case("RT-1048")) == DELIVERED


def test_trace_once_the_outcome_is_reported(fresh):  # noqa: F811
    """case.trace after the last acknowledgement and before Finance confirms (this used to raise NotImplementedError)."""
    for step in WRITES["exec_redeploy"]["calls"][:-2]:  # everything up to Finance's confirmation
        any_call(step["action"], step["input"], step["as"])
    got = call("case.trace", {"case_id": "RT-1048"}, "admin")
    assert got["ok"], got
    s9 = got["output"]["stages"][8]
    assert (s9["state"], s9["result"], s9["at"], s9["by"]) == (
        "person",
        f"Outcome reported (FI-47401); {DELIVERED}; waiting for Finance to confirm",
        "2026-10-07T09:00:00.000Z",
        "",
    )

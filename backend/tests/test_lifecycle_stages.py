"""P9-2.20 (story X-05; the ten-stage returned-asset journey, stages 1 to 3): the lease-end, return-authorised and transit
stage agents read the lease, return-authorisation and shipment records of a returned asset (registry entry I-7).

The records are canonical `compliance` facts of the case's asset (evidence entry I-3), put in place here as a sync would. The
tests play the worker (runtime.run_until_blocked) as tests/test_stage_chain.py does; the model tests use a `FunctionModel`
(no test reaches a provider). Every test ends with the starting state.
"""

import json
import re
from collections.abc import Callable
from typing import Any

import pytest
from pydantic_ai import ModelResponse, ToolCallPart, models
from pydantic_ai.models.function import AgentInfo, FunctionModel
from sqlalchemy import text

from di.core.db import SessionLocal
from di.services.actions.registry import ACTIONS
from di.services.agents import chain, lifecycle_evidence, registry, runtime
from di.services.agents.forbidden import FORBIDDEN_ACTIONS, check_person_only
from di.services.agents.playbooks import stage_chain
from di.services.agents.pydantic_ai_loop import PydanticAILoop
from di.services.agents.stages import CHAIN, lease_end, return_auth, transit
from di.services.canonical import store as canonical
from di.services.canonical.schema import compliance_key
from di.services.canonical.store import Fact
from di.services.cases import store
from tests import starting

models.ALLOW_MODEL_REQUESTS = False
pytestmark = pytest.mark.usefixtures("no_synced_conflicts")  # see conftest: synced conflicts and the hold policy

BOOK = "RT-1048"  # a book case: no lease records
BLOCKED = "RT-1051"  # evidence is missing, so `evidence.request` has something to ask for
NEW = ("lease_end", "return_auth", "transit")
AT = "2026-09-30T08:00:00Z"
LEASE = {
    "serial": "SN-77", "model": "VM-22", "site": "Pune plant", "usage": "6,200 h", "lease_end": "2026-10-01",
    "terms": "36 months",
}  # fmt: skip
INTENT = {"intent": "return", "note": "The customer returns the motor because the line is closing."}
AUTH = {"ra_number": "RA-5001", "fees": 450, "replacement_order": "PO-9001", "book_value": 8200, "acquired_on": "2023-10-01"}
SHIPMENT = {"pickup_on": "2026-10-02", "eta": "2026-10-20", "freight_cost": 310, "carrier": "Northline"}
LATE = SHIPMENT | {"eta": "2026-10-03"}  # before the pinned clock (7 Oct 2026)


def _clean() -> None:
    with SessionLocal() as s:
        s.execute(text("DELETE FROM agent_run_step"))
        s.execute(text("DELETE FROM agent_run"))  # the stage records cascade
        s.execute(text("DELETE FROM agent_proposal"))
        s.execute(text("DELETE FROM work_item WHERE type = 'transit_delayed'"))
        s.execute(text("DELETE FROM provenance WHERE model = 'compliance'"))
        s.execute(text("DELETE FROM canonical WHERE model = 'compliance'"))
        s.commit()


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    _clean()
    yield
    runtime.set_loop(None)
    starting.reset()
    _clean()


def _asset(case_id: str) -> str:
    with SessionLocal() as s:
        c = store.get(s, case_id)
    assert c is not None
    return str(c["assetId"])


def _put(case_id: str, type: str, value: dict[str, Any], result: str = "pass") -> None:
    asset = _asset(case_id)
    row = {"asset_key": asset, "type": type, "result": result, "at": AT, "value": value}
    with SessionLocal() as s:
        canonical.apply(s, "manual", [Fact("compliance", compliance_key(asset, type), f, v) for f, v in row.items()])
        s.commit()


def _drive(case: str = BOOK) -> str:
    with SessionLocal() as s:
        run_id = runtime.start(s, "recover-chain", "stage_chain", case, account="planner-a")
        s.commit()
        runtime.run_until_blocked(s, run_id)
    return run_id


def _records(run_id: str) -> dict[str, chain.StageRecord]:
    with SessionLocal() as s:
        return {r.stage: r for r in chain.records_of(s, run_id)}


def _run(run_id: str) -> dict:
    with SessionLocal() as s:
        return dict(s.execute(text("SELECT * FROM agent_run WHERE id = :i"), {"i": run_id}).mappings().one())


def _tools(run_id: str) -> list[str]:
    with SessionLocal() as s:
        return list(s.execute(text("SELECT tool FROM agent_run_step WHERE run_id = :i ORDER BY n"), {"i": run_id}).scalars())


def _items() -> list[dict]:
    with SessionLocal() as s:
        q = text("SELECT case_id, kind, type, title, owner_role FROM work_item WHERE type = 'transit_delayed'")
        return [dict(r) for r in s.execute(q).mappings()]


def _case(records: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """A case document with evidence records, as the stage modules read it (no database)."""
    return {
        "id": "RT-1",
        "evidenceRecords": [{"type": t, "source": "sim", "at": AT, "result": "pass", "value": v} for t, v in records.items()],
    }


def test_x_05_lease_end_output_and_confidence():
    """Stage 1 reads the lease record and the customer's intent: seven fields, confidence found over required."""
    full = _case({"lease_record": LEASE, "customer_intent": INTENT})
    out = lease_end.output({}, full)
    assert out == {"serial": "SN-77", "model": "VM-22", "site": "Pune plant", "usage": "6,200 h", "intent": "return",
                   "lease_end": "2026-10-01", "terms": "36 months"}  # fmt: skip
    assert lease_end.confidence({}, full) == 1.0
    no_intent = _case({"lease_record": LEASE})
    assert lease_end.output({}, no_intent)["intent"] is None and lease_end.confidence({}, no_intent) == pytest.approx(6 / 7)
    assert lease_end.sources({}, full) == [
        {"fact": "Lease record", "source": "sim", "at": "2026-09-30T08:00:00+00:00"},
        {"fact": "Customer intent", "source": "sim", "at": "2026-09-30T08:00:00+00:00"},
    ]
    # not a lease return: skipped with no call
    book = _case({})
    nxt = lease_end.next_call(0, {}, book)
    assert nxt.skipped and nxt.note == "not a lease return"  # type: ignore[union-attr]


def test_x_05_lease_end_missing_intent_requests_evidence():
    """A lease record without the customer's intent: 6/7, and one `evidence.request` (the case has evidence to ask for)."""
    _put(BLOCKED, "lease_record", LEASE)
    run_id = _drive(BLOCKED)
    rec = _records(run_id)["lease_end"]
    assert rec.confidence == pytest.approx(0.857, abs=0.001) and rec.status == "done"
    assert rec.output["intent"] is None and rec.output["serial"] == "SN-77"
    assert _tools(run_id)[:2] == ["case.evidence", "evidence.request"]


def test_x_05_return_auth_reads_fees_and_book_value():
    _put(BOOK, "lease_record", LEASE)
    _put(BOOK, "customer_intent", INTENT)
    _put(BOOK, "return_authorisation", AUTH)
    rec = _records(_drive())["return_auth"]
    assert rec.output == AUTH and rec.confidence == 1.0 and rec.status == "done"
    assert (rec.agent, rec.autonomy) == ("stage-return", "limits")
    assert rec.sources and rec.sources[0]["fact"] == "Return authorisation"
    part = _case({"return_authorisation": {k: v for k, v in AUTH.items() if k != "fees"}})
    assert return_auth.confidence({}, part) == pytest.approx(4 / 5)


def test_x_05_transit_waits_until_receipt():
    """A shipment and no goods receipt: the stage waits, and the receipt landing resumes the chain into intake."""
    _put(BOOK, "lease_record", LEASE)
    _put(BOOK, "shipment", SHIPMENT)
    run_id = _drive()
    rec = _records(run_id)
    assert rec["transit"].status == "waiting" and rec["transit"].output["delayed"] is False
    assert rec["transit"].output["carrier"] == "Northline" and "intake" not in rec
    assert _run(run_id)["status"] == "waiting" and _run(run_id)["state"]["waiting"] == "transit"
    _put(BOOK, "goods_receipt", {"received_on": "2026-10-06"})
    with SessionLocal() as s:
        assert lifecycle_evidence.wake_transit(s, _asset(BOOK)) == 1
        s.commit()
        runtime.run_until_blocked(s, run_id)
    rec = _records(run_id)
    assert rec["transit"].status == "done" and "intake" in rec and "condition" in rec
    assert _run(run_id)["state"]["waiting"] == "approval"  # on to the book case's usual wait


def test_x_05_transit_delay_opens_one_exception():
    """ETA before the workspace clock and no receipt: delayed, one "Transit delayed" item for the Planner; a second run
    opens no second item."""
    _put(BOOK, "lease_record", LEASE)
    _put(BOOK, "shipment", LATE)
    first = _drive()
    rec = _records(first)["transit"]
    assert rec.output["delayed"] is True and rec.status == "waiting"
    assert "transit.flagDelay" in _tools(first)
    assert _items() == [{"case_id": BOOK, "kind": "exception", "type": "transit_delayed", "title": "Transit delayed",
                         "owner_role": "Planner"}]  # fmt: skip
    _drive()
    assert len(_items()) == 1


def test_x_05_book_cases_skip_lifecycle_stages():
    """RT-1048 has no lease records: the three stages are skipped with the reason, no call is made, the rest is as before."""
    run_id = _drive()
    rec = _records(run_id)
    for sid in NEW:
        assert rec[sid].status == "skipped" and rec[sid].confidence is None, sid
        assert rec[sid].output == {"reason": "not a lease return"}
    assert list(rec)[:4] == [*NEW, "intake"]
    tools = _tools(run_id)
    assert tools[0] == "case.evidence" and tools.count("case.evidence") == 1  # intake's, no lease-stage read
    assert "transit.flagDelay" not in tools
    assert _run(run_id)["state"]["waiting"] == "approval"


def test_x_05_lifecycle_defaults():
    ids = [m.ID for m in CHAIN]
    assert ids[:4] == [*NEW, "intake"]
    assert [chain.AGENT_IDS[i] for i in NEW] == ["stage-lease", "stage-return", "stage-transit"]
    assert [chain.DEFAULT_AUTONOMY[i] for i in NEW] == ["alone", "limits", "alone"]
    assert stage_chain.LEGACY_POSITION["evidence"] == (3, 0)  # a run from before the chain: the autopilot's step is intake's


def test_x_05_lifecycle_agents_never_delete_or_approve():
    """R16: each new stage's tools pass `check_person_only` and the forbidden list; the seeded agents hold only those tools."""
    for mod in (lease_end, return_auth, transit):
        assert not [a for a in mod.ACTIONS if a.startswith(FORBIDDEN_ACTIONS)]
        check_person_only({a: ACTIONS[a] for a in mod.ACTIONS})
    with SessionLocal() as s:
        agents = {a: registry.get(s, a) for a in ("stage-lease", "stage-return", "stage-transit")}
    for agent in agents.values():
        assert agent is not None and agent.kind == "internal" and agent.enabled
        assert not [t for t in agent.tools if t.startswith(FORBIDDEN_ACTIONS)]
        check_person_only({t: ACTIONS[t] for t in agent.tools})
    assert agents["stage-transit"] and "transit.flagDelay" in agents["stage-transit"].tools


def _script(by_stage: dict[str, Callable[[AgentInfo], ModelResponse]]) -> None:
    def fn(messages: list, info: AgentInfo) -> ModelResponse:
        m = re.search(r"Stage: (\w+)\.", str(messages))
        assert m, "the prompt names the stage"
        handler = by_stage.get(m.group(1))
        if handler:
            return handler(info)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"summary": "Nothing."})])

    runtime.set_loop(PydanticAILoop(lambda _s, _run, _role: FunctionModel(fn)))


def test_x_05_lifecycle_stage_reasoner_reads_intent_note():
    """With a model, the customer's intent note becomes a finding with its source; the rules' output stays."""
    _put(BOOK, "lease_record", LEASE)
    _put(BOOK, "customer_intent", INTENT)
    finding = {"text": "The customer returns the motor because the line is closing.", "source": "customer_intent"}
    _script({"lease_end": lambda info: ModelResponse(
        parts=[ToolCallPart(info.output_tools[0].name, {"summary": "A closing line.", "findings": [finding]})])})  # fmt: skip
    rec = _records(_drive())["lease_end"]
    assert rec.kind == "llm" and rec.output["reading"]["findings"] == [finding]
    assert rec.output["intent"] == "return" and rec.confidence == 1.0
    assert json.dumps(rec.output["model"])  # the model that answered is named

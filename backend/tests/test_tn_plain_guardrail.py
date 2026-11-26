"""Plan 9, P9-10.14 (story TN-14, registry entries I-4 and I-13): the current-generation resale guardrail in plain words.

A planner types "Resale of current-generation cards needs approval from network planning". The configuration agent reads the
words (a model first when the router has one, R16; code reads them too and its reading wins) and places an Approval guardrail at
the Decide stage, scoped to the resell route and to cards whose `market.generation` is `current`, approved by `network_planning`.
It is an overlay operation (`add_approver` with a new guardrail), so it is held for a person (maker-checker: the maker cannot
approve, an agent never does, `forbidden.py`). A sentence that would waive a locked guardrail is `blocked`, never an operation.
The replay count (14, *modelled*) is the telecom history of P9-10.13; every number is code. Every model here is a `FunctionModel`.
Legal note: export-control wording is the pack's data; Kinective's Legal team reviews it before it is relied on.
"""

from typing import Any

import pytest
from sqlalchemy import text

from di.connectors import extra
from di.core.db import SessionLocal, engine
from di.services.agents import runtime
from di.services.agents.config_agent import draft_change_set
from di.services.agents.forbidden import forbidden
from di.services.agents.pydantic_ai_loop import PydanticAILoop
from di.services.modeler import plain_guardrail
from di.services.modeler.overlay import AddApprover, OverlayError, apply_overlay, ops_json, parse_ops
from di.services.modeler.pack import load_pack
from di.services.modeler.replay_samples import telecom_network as G
from di.services.modeler.stages import STAGE_KEYS
from di.services.replay import telecom as T
from di.services.replay.run import as_of_facts
from tests.helpers import call
from tests.test_tn_compose import _draft, _drafter, _scripted
from tests.test_tn_export import _bid, _bids, _unit, broker  # noqa: F401
from tests.test_tn_intake import _case, _ok, _open, _write, fresh  # noqa: F401

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")

PACK = load_pack("telecom_network")
ORG = "Customer A"
SENTENCE = "Resale of current-generation cards needs approval from network planning"
ACTION = "Resell what the forecast doesn't need; keep the rest as regional spares"
ITEM = "AP-TN-CURGEN"
MAKER_CHECKER = "Maker-checker: you made these changes, so you cannot approve them."


def _guardrail_op(**over: Any) -> dict[str, Any]:
    return {
        "id": "op-1", "op": "add_approver", "guardrail_id": ITEM, "type": "Approval", "stage": "decide",
        "when": {"all": [{"route": "resell"}, {"fact": "market.generation", "op": "eq", "value": "current"}]},
        "approver": "network_planning", "text": SENTENCE,
    } | over  # fmt: skip


@pytest.fixture(autouse=True)
def no_loop():
    runtime.set_loop(PydanticAILoop(lambda _s, _run, _role: None))  # no model: the deterministic path (R16)
    yield
    runtime.set_loop(None)


def _draft_of(words: str = SENTENCE):
    return draft_change_set(words, ORG, packs=[PACK], answer=None)


# ---------------------------------------------------------------- the sentence places the guardrail
def test_tn_14_sentence_places_approval_guardrail():
    cs = _draft_of()
    assert cs.pack == "telecom_network" and cs.by_model is False and cs.blocked == [] and cs.assumed == []
    (op,) = cs.ops
    assert isinstance(op, AddApprover)
    assert op.model_dump(mode="json", exclude_none=True) == {
        **_guardrail_op(),
        "id": "op-1",
        "by": "",
        "note": "",
        "target": "",
        "role": "",
    }
    assert STAGE_KEYS.index(op.stage) + 1 == 5 and op.type == "Approval"  # stage 5, Decide
    placed = apply_overlay(PACK, cs.ops)
    g = next(x for x in placed.guardrails if x.id == ITEM)
    assert (g.type, g.stage, g.locked, g.approvers, g.text) == ("Approval", "decide", False, ["network_planning"], SENTENCE)
    assert [x for x in PACK.guardrails if x.locked] == [x for x in placed.guardrails if x.locked]  # no locked guardrail moved
    (d,) = placed.diversions
    assert (d.kind, d.route, d.guardrail_id, d.owner_role) == ("approval", "resell", ITEM, "network_planning")
    assert ops_json(parse_ops(ops_json(cs.ops))) == ops_json(cs.ops)  # stored and read back


def test_tn_14_other_words_other_scope_and_unknown_role():
    previous = _draft_of("Resale of previous-generation cards needs approval from network planning")
    (op,) = previous.ops
    assert op.when.all[1].value == "previous" and op.guardrail_id == "AP-TN-PREGEN"
    assert _draft_of("Resale of current-generation cards needs approval from the moon").ops == []  # no such role in the pack
    assert _draft_of("Resale of cards needs approval from network planning").ops == []  # no scope: nothing is guessed


def test_tn_14_a_sentence_that_waives_a_locked_guardrail_is_blocked():
    export = next(g.text for g in PACK.guardrails if g.id == "G-NET-EXP")
    for words in (
        "Resale of current-generation cards no longer needs export control approval",
        "Skip the export-control check for current-generation cards",
        "Resale of current-generation cards does not need approval from trade compliance",
    ):
        cs = _draft_of(words)
        assert cs.ops == [] and [b.guardrail for b in cs.blocked] == [export], words


def test_tn_14_an_op_that_weakens_nothing_is_the_only_new_guardrail_shape():
    for bad in (
        {"type": "Compliance"},  # a customer never adds a locked kind
        {"stage": "receive"},  # an approval is at Decide
        {"approver": "ghost_role"},
        {"guardrail_id": "G-NET-EXP"},  # the id of a pack guardrail
        {"when": {"all": [{"route": "ship"}]}},  # not a route of the pack
    ):
        with pytest.raises((OverlayError, ValueError)):
            apply_overlay(PACK, parse_ops([_guardrail_op(**bad)]))


# ---------------------------------------------------------------- the model reads the words, the checks win (R16)
def test_tn_14_model_draft_is_accepted_when_it_checks_out():
    runtime.set_loop(_scripted(_draft(ops=[_guardrail_op()])))
    cs = draft_change_set(SENTENCE, ORG, packs=[PACK], answer=None, drafter=_drafter())
    assert cs.by_model is True and [o.guardrail_id for o in cs.ops] == [ITEM] and cs.blocked == []  # type: ignore[union-attr]


def test_tn_14_model_draft_naming_a_role_the_pack_lacks_is_refused_then_the_code_reading_answers():
    seen: list[int] = []
    runtime.set_loop(_scripted(_draft(ops=[_guardrail_op(approver="ghost_role")]), seen))
    cs = draft_change_set(SENTENCE, ORG, packs=[PACK], answer=None, drafter=_drafter())
    assert len(seen) == 2 and cs.by_model is False  # one retry, then the deterministic path
    assert [o.guardrail_id for o in cs.ops] == [ITEM]  # type: ignore[union-attr]


def test_tn_14_model_cannot_drop_the_code_reading_of_a_waiver():
    runtime.set_loop(_scripted(_draft(ops=[])))
    words = "Skip the export-control check for current-generation cards"
    cs = draft_change_set(words, ORG, packs=[PACK], answer=None, drafter=_drafter())
    assert (
        cs.by_model is True
        and cs.ops == []
        and [b.guardrail for b in cs.blocked] == [next(g.text for g in PACK.guardrails if g.id == "G-NET-EXP")]
    )


# ---------------------------------------------------------------- the replay count
def test_tn_14_replay_counts_14():
    data = G.rows()
    (op,) = _draft_of().ops
    items = T.items(data)
    taken = [(i["actual_route"], as_of_facts(i)[0]) for i in items]  # the route taken, the facts known when it was
    assert plain_guardrail.would_change(op, taken, PACK) == G.resales_of_current_cards(data) == 14  # *modelled*
    other = _draft_of("Resale of previous-generation cards needs approval from network planning").ops[0]
    assert plain_guardrail.would_change(other, taken, PACK) != 14  # the scope is the fact: another value, another count
    # the decider's replay under the guardrail holds decisions for a person and changes no route or value
    placed = apply_overlay(PACK, [op])
    base, after = T.replay(items), T.replay(items, pack=placed)
    assert after.report.held_for_person > base.report.held_for_person and after.report.n_decided == base.report.n_decided == 1260
    assert after.decided == base.decided


# ---------------------------------------------------------------- maker-checker, then live
def _items(cid: str | None = None) -> list[dict[str, Any]]:
    sql = "SELECT case_id, kind, status, owner_role, title, cause, action FROM work_item WHERE type = :t"
    with SessionLocal() as s:
        rows = (
            s.execute(text(sql + (" AND case_id = :c" if cid else "") + " ORDER BY id"), {"t": ITEM, "c": cid}).mappings().all()
        )
    return [dict(r) for r in rows]


def _clean() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM work_item WHERE type = :t"), {"t": ITEM})
        conn.execute(text("DELETE FROM customer_overlay"))
        conn.execute(text("DELETE FROM provenance WHERE source_id = 'tn_spares'"))
        conn.execute(text("DELETE FROM canonical WHERE model = 'market' AND key LIKE '%RAD-7700%'"))


@pytest.fixture
def live(broker):  # noqa: F811
    with SessionLocal() as s:
        extra.register(s, "tn_spares", ORG)
        s.commit()
    _clean()
    yield
    _clean()


def _unit_of(n: int, generation: str) -> dict[str, Any]:
    _write("tn_spares", "catalogue", {"model": "RAD-7700", "newPrice": 9800, "generation": generation, "org_unit_id": ORG})
    _write(
        "tn_spares", "forecast6m", {"region": "North", "model": "RAD-7700", "need": 0, "org_unit_id": ORG}
    )  # no region needs it
    _bids("RAD-7700", _bid("BID-7700-US", 1900, "clear", country="US"))
    return _unit(n, "RAD-7700", exportClassConfirmed="EAR99")


def test_tn_14_maker_checker_then_live(live):
    cs = _draft_of()
    body = {"pack_key": "telecom_network", "org_unit_id": ORG, "ops": ops_json(cs.ops)}
    ref = {"pack_key": "telecom_network", "org_unit_id": ORG}
    _ok(call("overlay.save", body, "admin"))
    assert _ok(call("overlay.submit", ref, "admin"))["status"] == "review"
    assert call("overlay.approve", ref, "admin")["error"]["message"] == MAKER_CHECKER  # the maker cannot approve
    assert forbidden("overlay.approve") and forbidden("overlay.reject")  # no agent ever does
    # before it is published nothing changes: a current-generation resale is not held
    u = _unit_of(1, "current")
    before = _case(_ok(_open(u))["case_id"])
    assert before["recommendation"], (
        before.get("gateHold"),
        [(r["id"], r.get("excluded"), r.get("reason")) for r in before["routes"]],
    )
    assert before["recommendation"]["id"] == "resell" and before.get("approvalHolds") is None and _items(before["id"]) == []
    assert _ok(call("overlay.approve", ref, "approver"))["status"] == "pub"
    # published: a matching case holds, with one item for the role of network planning
    c = _case(_ok(_open(_unit_of(2, "current")))["case_id"])
    assert c["recommendation"]["id"] == "resell"
    assert [h["id"] for h in c["approvalHolds"]] == [ITEM] and c["approvalHolds"][0]["owner"] == "network_planning"
    (item,) = _items(c["id"])
    assert (item["status"], item["owner_role"], item["action"]) == ("open", "Approver", ACTION)
    assert SENTENCE in item["title"] and "Recommended: " in item["cause"]
    # a card of the previous generation is not
    other = _case(_ok(_open(_unit_of(3, "previous")))["case_id"])
    assert other["recommendation"]["id"] == "resell" and other.get("approvalHolds") is None and _items(other["id"]) == []

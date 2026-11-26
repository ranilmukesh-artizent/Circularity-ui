"""Plan 9, P9-9.16 (story UC-13): "Any car sent to auction with fewer than 40,000 miles needs approval from the remarketing
manager", in words.

The remarketing director states a guardrail in plain words. The configuration agent (P9-2.7) reads the sentence into one typed
overlay operation, `add_approver` in its new-guardrail shape (shared with P9-10.14 and P9-11.14): an Approval guardrail
`AP-UC-AUCTION40K` at the decide stage (stage 5), when the route is auction and `asset.mileage_at_return < 40000`, approved by
`remarketing_manager`. Code reads the words and wins over any model. The history counts the 31 past auction sales of a car under
40,000 miles (*modelled*, a sample). The guardrail is the customer's overlay, so it goes through maker-checker like any overlay:
the author cannot approve it and no agent does (golden rule 10). Once published, a car whose best channel is auction at 31,000
miles is held for the remarketing manager with an item in My work. Compliance wording of the pack is reviewed by Kinective's
Legal team before it is relied on.
"""

from typing import Any

import pytest
from pydantic_ai import models
from pydantic_ai.models.function import FunctionModel  # noqa: F401 - FunctionModel keeps the model path off the network
from sqlalchemy import text

from di.core.db import SessionLocal
from di.repositories.live_rules import live_pack
from di.services.actions.overlays import MAKER_CHECKER
from di.services.agents import runtime
from di.services.agents.config_agent import draft_change_set
from di.services.agents.forbidden import FORBIDDEN_ACTIONS
from di.services.agents.pydantic_ai_loop import PydanticAILoop
from di.services.modeler import plain_guardrail
from di.services.modeler import plain_words_used_cars as words
from di.services.modeler.overlay import AddApprover, apply_overlay, ops_json
from di.services.modeler.pack import load_pack
from di.services.modeler.replay_samples import used_cars as U
from tests import flowkit
from tests import ucfixtures as uc
from tests.helpers import call, client, h

pytestmark = pytest.mark.usefixtures("no_synced_conflicts")
models.ALLOW_MODEL_REQUESTS = False

ORG, PACK = "Customer A", "used_cars"
SENTENCE = "Any car sent to auction with fewer than 40,000 miles needs approval from the remarketing manager"
WHEN = {"all": [{"route": "auction"}, {"fact": "asset.mileage_at_return", "op": "lt", "value": 40000.0}]}
NEW = {"guardrail_id": "AP-UC-AUCTION40K", "type": "Approval", "stage": "decide", "when": WHEN, "approver": "remarketing_manager"}
ACTION = "Auction when retail days-to-sale is far above average at every lot"


@pytest.fixture(autouse=True)
def fresh():
    uc.start()
    flowkit.reset_flows()
    runtime.set_loop(PydanticAILoop(lambda _s, _run, _role: None))  # no model: the deterministic path (R16)
    yield
    runtime.set_loop(None)
    with SessionLocal() as s:
        s.execute(text("DELETE FROM work_item WHERE type = 'AP-UC-AUCTION40K'"))
        s.commit()
    uc.finish()
    flowkit.reset_flows()


def _draft(words_: str = SENTENCE):
    return draft_change_set(words_, ORG, packs=[load_pack(PACK)], answer=None)


def _the_op(cs: Any) -> AddApprover:
    got = [o for o in cs.ops if isinstance(o, AddApprover) and o.guardrail_id is not None]
    assert len(got) == 1, cs.ops
    return got[0]


def test_uc_13_sentence_places_approval_guardrail():
    cs = _draft()
    assert cs.pack == PACK and cs.by_model is False and cs.blocked == [] and cs.assumed == []
    op = _the_op(cs)
    assert op.model_dump(mode="json", exclude={"id", "by", "note", "target", "role"}) == {
        "op": "add_approver",
        "text": SENTENCE,
        **NEW,
    }
    pack = load_pack(PACK)
    assert [s.key for s in pack.stages].index(op.stage or "") == 4  # stage 5 of 7
    placed = apply_overlay(pack, cs.ops)
    g = next(x for x in placed.guardrails if x.id == "AP-UC-AUCTION40K")
    assert (g.type, g.locked, g.owner, g.approvers) == ("Approval", False, "remarketing_manager", ["remarketing_manager"])
    d = next(x for x in placed.diversions if x.guardrail_id == "AP-UC-AUCTION40K")
    assert (d.kind, d.route, d.stage) == ("approval", "auction", "decide")
    assert d.when == [{"fact": "asset.mileage_at_return", "op": "lt", "value": 40000.0}]
    assert "AP-UC-AUCTION40K" not in [x.id for x in pack.guardrails]  # apply_overlay never changes the pack given
    assert [x.id for x in pack.guardrails] == [x.id for x in placed.guardrails if x.id != "AP-UC-AUCTION40K"]


def test_uc_13_a_waiver_and_other_sentences_place_nothing():
    assert (
        _draft("Any car sent to auction with fewer than 40,000 miles does not need approval from the remarketing manager").ops
        == []
    )
    assert _draft("We remarket returned leases").ops == []
    pack = load_pack(PACK)
    assert (
        plain_guardrail.read_clause(
            "Any car sent to auction with more than 90,000 miles needs approval from the remarketing manager", pack
        )
        is not None
    )


def test_uc_13_replay_counts_31():
    """Over the 2,140 cars of the sample history exactly 31 auction sales are of a car under 40,000 miles (*modelled*)."""
    pack = apply_overlay(load_pack(PACK), _draft().ops)
    cars = U.rows()
    assert len([c for c in cars if c["actual_route"] == "auction" and c["asset.mileage_at_return"] < 40000]) == 31
    assert plain_guardrail.would_change(_the_op(_draft()), words.history_items(cars), pack) == 31  # "31 decisions would change"
    over = _draft("Any car sent to auction with more than 40,000 miles needs approval from the remarketing manager").ops[0]
    assert plain_guardrail.would_change(over, words.history_items(cars), pack) != 31  # the number and its side are the scope


def _save(ops: list, maker: str = "planner.a") -> dict[str, Any]:
    body = {"pack_key": PACK, "org_unit_id": ORG}
    uc.ok(call("overlay.save", body | {"ops": ops_json(ops)}, maker))
    uc.ok(call("overlay.submit", body, maker))
    return body


def test_uc_13_maker_checker_then_live():
    body = _save(_draft().ops)
    with SessionLocal() as s:
        assert "AP-UC-AUCTION40K" not in [g.id for g in live_pack(s, {"template": PACK, "owner": ORG}).guardrails]  # in review
    refused = call("overlay.approve", body, "planner-a")  # the author
    assert refused["ok"] is False and refused["error"]["message"] == "The Planner view cannot approve customer overlays."
    assert MAKER_CHECKER.startswith("Maker-checker")  # the rule for an author who may approve: see the overlay tests
    assert "overlay.approve".startswith(FORBIDDEN_ACTIONS)
    agent = client.post(
        "/api/actions/overlay.approve", json=body, headers=h("approver") | {"X-Circularity-Preparer": "coordinator"}
    )
    assert agent.status_code == 403 and agent.json()["error"]["code"] == "approval_required", agent.json()
    uc.ok(call("overlay.approve", body, "approver"))  # a different person
    with SessionLocal() as s:
        assert "AP-UC-AUCTION40K" in [g.id for g in live_pack(s, {"template": PACK, "owner": ORG}).guardrails]
    # no lot has sales history for this car, so auction is its best channel; it was returned at 31,000 miles
    c = uc.open_car(31, 1, miles=31000, photo=31000, last_service=31000, lots=(), bid=None)
    assert c["recommendation"]["id"] == "auction", c["recommendation"]
    holds = [x for x in c["approvalHolds"] if x["id"] == "AP-UC-AUCTION40K"]
    assert len(holds) == 1 and holds[0]["owner"] == "remarketing_manager" and holds[0]["action"] == ACTION, c.get("approvalHolds")
    got = uc.items(c["id"], "AP-UC-AUCTION40K")
    assert [(i["owner_role"], i["action"], i["status"]) for i in got] == [("Approver", ACTION, "open")]
    assert "decision.approve".startswith(FORBIDDEN_ACTIONS)
    assert uc.get(c["id"])["approval"] is None  # nobody approved it: it waits for the remarketing manager
    over = uc.open_car(32, 1, miles=52000, photo=52000, last_service=52000, lots=(), bid=None)  # the same channel, more miles
    assert over["recommendation"]["id"] == "auction"
    assert "AP-UC-AUCTION40K" not in [x["id"] for x in over.get("approvalHolds", [])]

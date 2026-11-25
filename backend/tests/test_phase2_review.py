"""Fixes from the phase 2 gate review (plan 9, docs/agents/plans/09-work/review-phase-2.md).

1. A write that only adds caution (fraud.hold) is never held for a person, whatever the stage's concerns or taint.
3. A proposal is decided once: accept or reject re-checks `pending` under the row lock, and `decide` updates only a
   pending row.
4. conflict.resolve is a person's: it clears the "sources disagree" hold.
"""

import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text

from di.core.db import SessionLocal
from di.services.actions import proposals as proposal_actions
from di.services.actions.hold import hold_check
from di.services.actions.pipeline import SYSTEM, CallContext
from di.services.actions.registry import ACTIONS, ActionError
from di.services.agents import proposals
from di.services.agents.forbidden import CAUTION_ONLY, PERSON_ONLY_NAME, check_person_only, forbidden
from di.services.agents.stage_context import StageContext
from tests import starting

CASE = "RT-1048"


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    yield
    starting.reset()


def _worried_stage() -> StageContext:
    """A stage that holds every ordinary write: recommend only, low confidence, a model concern."""
    return StageContext(
        stage="intake",
        autonomy="recommend",
        confidence=0.1,
        threshold=0.75,
        value=Decimal("100"),
        value_limit=Decimal("50"),
        bulk_limit=None,
        model_concerns=["The return record looks odd."],
    )


def test_caution_only_writes_are_never_held():
    with SessionLocal() as s:
        ctx = CallContext(actor=SYSTEM, session=s, preparer="recover-chain", stage=_worried_stage(), taint=True)
        for action_id in CAUTION_ONLY:
            assert hold_check(ACTIONS[action_id], {"case_id": CASE}, ctx) == [], action_id
        # the same stage holds an ordinary write: the exemption is for caution only
        assert hold_check(ACTIONS["evidence.request"], {"case_id": CASE}, ctx)


def _proposal(s, status: str) -> int:
    return int(
        s.execute(
            text(
                "INSERT INTO agent_proposal (agent, action, input, case_id, status, requested_by, reasons) "
                "VALUES ('recover-chain', 'evidence.request', CAST(:i AS jsonb), :c, :st, 'admin', '[]') RETURNING id"
            ),
            {"i": json.dumps({"case_id": CASE}), "c": CASE, "st": status},
        ).scalar_one()
    )


@pytest.mark.parametrize("handler", [proposal_actions.accept, proposal_actions.reject])
def test_a_decided_proposal_is_not_decided_again(handler):
    """Two people decide at once: the second, past the guard, finds the row already decided under its lock."""
    with SessionLocal() as s:
        pid = _proposal(s, "accepted")
        ctx = CallContext(actor=SYSTEM, session=s)
        with pytest.raises(ActionError) as e:
            handler({"id": pid, "reason": "A second decision."}, ctx)
        assert e.value.code == "conflict"
        s.rollback()


def test_decide_updates_only_a_pending_proposal():
    with SessionLocal() as s:
        pid = _proposal(s, "accepted")
        proposals.decide(s, pid, "rejected", "approver", datetime.now(UTC), {})
        assert s.execute(text("SELECT status FROM agent_proposal WHERE id = :i"), {"i": pid}).scalar_one() == "accepted"
        s.rollback()


def test_conflict_resolve_is_a_persons():
    assert forbidden("conflict.resolve")
    assert PERSON_ONLY_NAME.search("conflict.resolve")
    check_person_only(ACTIONS)  # every resolve, waive, clear, dismiss or accept action is forbidden to agents

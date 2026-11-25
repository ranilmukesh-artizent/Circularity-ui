"""P9-2.19 (story X-15; R16 model first, code holds the line): the model's review of a fraud triage.

After the computed triage the intake stage's model reads the case, the fired and unfired signals and the free text, and writes
why the case looks or does not look like fraud. Code checks it and wins: cited sources must exist and numbers must be given
ones (one retry, then no review); a review can raise a hold below the threshold (signal `model_review`) and never releases one;
the score and the rule version stay computed. A fraud-held case cannot be approved until a person releases it. Every model is
a `FunctionModel` (no test reaches a provider). Every test ends with the starting state.
"""

import re
from collections import Counter
from collections.abc import Callable
from typing import Any

import pytest
from pydantic_ai import ModelResponse, ToolCallPart, models
from pydantic_ai.models.function import AgentInfo, FunctionModel
from sqlalchemy import text

from di.core.db import SessionLocal
from di.services.agents import fraud_review, runtime
from di.services.agents.playbooks import fraud_reviewer
from di.services.agents.pydantic_ai_loop import PydanticAILoop
from di.services.modeler.fraud import FraudResult
from tests import starting
from tests.helpers import call
from tests.test_fraud_triage import (
    BLACKLIST,
    CASE,
    QUOTE,
    _clean,
    case_now,
    device_doc,
    held_case,
    intake,
    items,
    ok,
    open_case,
    publish,
)

models.ALLOW_MODEL_REQUESTS = False
pytestmark = pytest.mark.usefixtures("no_synced_conflicts")  # see conftest: synced conflicts and the hold policy

NOT_FRAUD = {"narrative": "The data fits an ordinary return.", "concerns": [], "raise_hold": False}
ODD = {
    "narrative": "The received capacity differs from the declared one.",
    "concerns": [{"text": "Quote check shows another capacity.", "sources": ["F-QM"]}],
    "raise_hold": True,
}
Handler = Callable[[AgentInfo, int], ModelResponse]


@pytest.fixture(autouse=True)
def fresh():
    starting.reset()
    _clean()
    yield
    runtime.set_loop(None)
    _clean()
    starting.reset()


def final(info: AgentInfo, **out: Any) -> ModelResponse:
    return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, out)])


def script(review: Handler) -> Counter[str]:
    """A scripted model: the fraud review goes to `review` (with how many requests it has made); the stage readings answer
    all clear. Returns the request counts."""
    calls: Counter[str] = Counter()

    def fn(messages: list, info: AgentInfo) -> ModelResponse:
        if re.search(r"FRAUD-REVIEW", str(messages)):
            calls["review"] += 1
            return review(info, calls["review"])
        calls["stage"] += 1
        return final(info, summary="Nothing stands out on this stage.")

    runtime.set_loop(PydanticAILoop(lambda _s, _run, _role: FunctionModel(fn)))
    return calls


def no_model() -> None:
    runtime.set_loop(PydanticAILoop(lambda _s, _run, _role: None))


def reviews() -> list[dict[str, Any]]:
    with SessionLocal() as s:
        q = text("SELECT id, agent, playbook, status FROM agent_run WHERE playbook = 'fraud_reviewer'")
        return [dict(r) for r in s.execute(q).mappings()]


def fraud_item_id(cid: str) -> int:
    with SessionLocal() as s:
        q = text("SELECT id FROM work_item WHERE case_id = :c AND type = 'fraud_hold'")
        return int(s.execute(q, {"c": cid}).scalar_one())


def test_fraud_review_raises_hold_below_threshold():
    """X-15: score 0.3 is under the 0.6 threshold; the review says hold: the case is held with signal model_review, the score
    and the rule version stay the computed ones."""
    publish(device_doc())
    cid = open_case("SN-R-1", QUOTE)  # 0.3 against 0.6
    script(lambda info, _n: final(info, **ODD))
    run_id, rec = intake(cid)
    assert rec.status == "held" and rec.output["fraud"] == {"score": 0.3, "threshold": 0.6, "rule_version": "v1", "held": True}
    f = case_now(cid)["fraud"]
    assert (f["status"], f["score"], f["rule_version"]) == ("held", 0.3, "v1")
    sig = {s["id"]: s for s in f["signals"]}
    assert set(sig) == {"F-QM", "model_review"}
    assert sig["model_review"]["value"] == ODD["narrative"] and "F-QM" in sig["model_review"]["source"]
    assert f["review"]["narrative"] == ODD["narrative"] and f["review"]["concerns"][0]["sources"] == ["F-QM"]
    assert f["review"]["raise_hold"] is True
    [item] = items(cid)
    assert item["status"] == "open" and item["owner_role"] == "Approver"
    with SessionLocal() as s:
        assert s.execute(text("SELECT state->>'waiting' FROM agent_run WHERE id = :i"), {"i": run_id}).scalar_one() == "fraud"
    assert [r["status"] for r in reviews()] == ["done"]


def test_fraud_review_below_threshold_without_hold_continues():
    """A review that raises no hold changes nothing: the case goes on, nothing is opened."""
    publish(device_doc())
    cid = open_case("SN-R-2", QUOTE)
    calls = script(lambda info, _n: final(info, **NOT_FRAUD))
    _, rec = intake(cid)
    assert rec.status == "done" and rec.output["fraud"]["held"] is False and rec.output["fraud"]["score"] == 0.3
    assert case_now(cid).get("fraud") is None and items(cid) == []
    assert calls["review"] == 1  # asked once for the run, not once per step


def test_fraud_review_never_releases():
    """X-15: a case the computed score holds stays held under a review that says it is not fraud; the review is kept beside
    the signals for the person."""
    publish(device_doc())
    cid = open_case("SN-R-3", BLACKLIST, QUOTE)  # 0.8 against 0.6
    script(lambda info, _n: final(info, **NOT_FRAUD))
    _, rec = intake(cid)
    f = case_now(cid)["fraud"]
    assert rec.status == "held" and f["status"] == "held" and f["score"] == 0.8
    assert {s["id"] for s in f["signals"]} == {"F-BL", "F-QM"}  # no model_review signal: it did not raise anything
    assert f["review"]["narrative"] == NOT_FRAUD["narrative"] and f["review"]["raise_hold"] is False
    [item] = items(cid)
    assert item["status"] == "open"


def test_fraud_review_unknown_source_dropped():
    """A concern that cites a source the case does not have: one retry, then no review and the computed result stands."""
    publish(device_doc())
    cid = open_case("SN-R-4", QUOTE)
    bad = ODD | {"concerns": [{"text": "Seen in the log.", "sources": ["no-such-signal"]}]}
    calls = script(lambda info, _n: final(info, **bad))
    _, rec = intake(cid)
    assert calls["review"] == 2  # the first answer and one retry
    assert rec.status == "done" and case_now(cid).get("fraud") is None and items(cid) == []
    assert reviews() == []  # no review: the run is not kept


def test_fraud_review_retry_then_accepted():
    """The first answer cites an unknown source; told why, the model cites a real one and the review stands."""
    publish(device_doc())
    cid = open_case("SN-R-5", QUOTE)
    bad = ODD | {"concerns": [{"text": "Seen in the log.", "sources": ["no-such-signal"]}]}
    calls = script(lambda info, n: final(info, **(bad if n == 1 else ODD)))
    _, rec = intake(cid)
    assert calls["review"] == 2 and rec.status == "held"
    assert case_now(cid)["fraud"]["review"]["narrative"] == ODD["narrative"]


def test_fraud_review_invented_number_retried():
    """R16: a number in the narrative that is in no case fact or signal is refused (a computed number is never the model's)."""
    publish(device_doc())
    cid = open_case("SN-R-6", QUOTE)
    bad = ODD | {"narrative": "Fraud losses of 98765 are likely."}
    calls = script(lambda info, _n: final(info, **bad))
    _, rec = intake(cid)
    assert calls["review"] == 2 and rec.status == "done" and case_now(cid).get("fraud") is None


def test_fraud_review_tools_read_only():
    spec = fraud_reviewer.spec()
    assert spec.tools == ("case.get", "case.evidence", "case.trace") and spec.output_type is fraud_review.FraudReview
    assert spec.untrusted_tools == {"case.evidence", "case.trace"} and spec.role == "stage"
    from di.services.actions.registry import ACTIONS

    assert all(ACTIONS[t].risk == "read" for t in spec.tools)
    for bad in ("fraud.release", "fraud.reject", "decision.approve", "work.resolve"):
        with pytest.raises(ValueError, match="read-only"):
            fraud_reviewer.build_spec(("case.get", bad))


def test_fraud_review_check_is_pure():
    """check_review names every problem: a missing source, an invented number; a good review has none."""
    result = FraudResult(0.3, [], "v1", False, 0.6)
    case = {"id": "X-1", "evidenceRecords": [], "facts": []}
    good = fraud_review.FraudReview(narrative="Score 0.3 is under 0.6.", concerns=[], raise_hold=False)
    assert fraud_review.check_review(good, case, result) == []
    bad = fraud_review.FraudReview(
        narrative="About 777 units.", concerns=[fraud_review.ReviewConcern(text="x", sources=["nope"])], raise_hold=True
    )
    errors = fraud_review.check_review(bad, case, result)
    assert len(errors) == 2 and "nope" in errors[0] and "777" in errors[1]


def test_fraud_and_exception_no_model_same_as_today():
    """R16: no model, the same answers as before: the computed triage alone holds; no review run is left; the exception
    draft is the pack's."""
    publish(device_doc())
    no_model()
    low, high = open_case("SN-R-7", QUOTE), open_case("SN-R-8", BLACKLIST, QUOTE)
    _, rec = intake(low)
    assert rec.status == "done" and case_now(low).get("fraud") is None
    _, rec = intake(high)
    f = case_now(high)["fraud"]
    assert rec.status == "held" and f["score"] == 0.8 and "review" not in f
    assert reviews() == []
    d = ok(call("exception.explain", {"exception_id": fraud_item_id(high)}, "approver"))
    assert d["by_model"] is False and d["model"] is None and d["pack_default"] is None


def test_fraud_held_case_cannot_be_approved_until_released():
    """X-15: a held case cannot be approved or overridden (conflict) until a person releases it."""
    cid = held_case()
    assert cid == CASE
    body = {"case_id": cid, "rationale": "The decision rules support this route fully.", "reviewed": True}
    for action in ("decision.approve", "decision.override"):
        r = call(action, body | ({"route": "recycle"} if action == "decision.override" else {}), "approver")
        assert r["ok"] is False and r["error"]["code"] == "conflict", r
        assert r["error"]["message"] == "Held for fraud review: release it first."
    assert case_now(cid).get("approval") is None
    ok(call("fraud.release", {"case_id": cid, "reason": "Checked with the customer; the serial is genuine."}, "approver"))
    r = call("decision.approve", body, "approver")
    assert r["ok"] is True, r

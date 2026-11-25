"""The model's fraud review (plan 9, P9-2.19; story X-15; R16; uses registry entries I-8, I-9, I-10).

    FraudReview(narrative, concerns, raise_hold)     what the model writes (typed, no number field)
    ReviewConcern(text, sources)
    check_review(review, case, result) -> [str]      pure: why a review is refused (empty: it is accepted)
    review_fraud(s, ctx, case, result, *, loop) -> FraudReview | None   the model's review of one triaged case, or None

After the computed triage (`di.services.modeler.fraud.triage`) the model reads the case through the read tools (`case.get`,
`case.evidence`, `case.trace`; the last two return text from source systems and are untrusted), the fired and the unfired
signals and the free text, and writes why the case looks or does not look like fraud. `raise_hold` asks for a hold on a case
the score did not hold; `di.services.actions.fraud.review_case` turns that into the signal `model_review`.

Code holds the line. A review is checked as it is returned (a validator, `checked_output.checked_type`): every cited source
(a signal id, an evidence key or record type, `fact.<n>`, a case field) exists on the case, and every number in the text is in
the case or the triage's result. A refusal is sent back with its reasons once; after the second, the review is dropped (None)
and the computed result stands. The review only adds caution: it never releases a hold, lowers the threshold or changes the
score or the rule version (golden rule 10); `fraud.release` and `fraud.reject` stay a person's.

The loop runs in an `agent_run` of its own (playbook `fraud_reviewer`, the agent of the chain's call) in a session of its own
(the loop commits after each model turn); the row stays only when a review was made.
Never does: call an action that writes, hold or release a case (the caller does), compute a score. No model, or any failure of
the loop: None.
"""

import json
import logging
import uuid
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text as sql
from sqlalchemy.orm import Session

from di.core.db import SessionLocal
from di.services.actions.pipeline import CallContext
from di.services.agents.checked_output import checked_type, invented_numbers
from di.services.agents.loop import AgentLoop
from di.services.agents.stage_reasoner import case_sources
from di.services.modeler.fraud import FraudResult

log = logging.getLogger(__name__)
PLAYBOOK = "fraud_reviewer"
VERSION = "1"
MAX_TEXT = 600
MARK = "FRAUD-REVIEW"  # the first word of the prompt


class ReviewConcern(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(max_length=MAX_TEXT, description="What looks wrong, in a plain sentence.")
    sources: list[str] = Field(default_factory=list, description="Signal ids, evidence ids or facts it rests on (from the list).")


class FraudReview(BaseModel):
    """What the model writes about one triaged case. No field holds a number: the score and the rule version are computed."""

    model_config = ConfigDict(extra="forbid")

    narrative: str = Field(max_length=MAX_TEXT, description="Why the case looks or does not look like fraud.")
    concerns: list[ReviewConcern] = Field(default_factory=list)
    raise_hold: bool = Field(default=False, description="True when a person must look at this case before it goes on.")


def review_sources(case: Mapping[str, Any], result: FraudResult) -> list[str]:
    """Every id a concern may cite: the signals (fired or not), then what the case has (`stage_reasoner.case_sources`)."""
    return list(dict.fromkeys([s.id for s in result.signals] + case_sources(case, {})))


def _facts(case: Mapping[str, Any], result: FraudResult) -> list[str]:
    return [
        json.dumps(case, default=str),
        json.dumps(result.as_dict(), default=str),
        json.dumps([s.as_dict() for s in result.signals]),
    ]


def check_review(review: FraudReview, case: Mapping[str, Any], result: FraudResult) -> list[str]:
    """Why the review is refused, one sentence each (pure): a cited source the case does not have, a number that is in neither
    the case nor the triage."""
    errors: list[str] = []
    known = {x.strip().lower() for x in review_sources(case, result)}
    missing = sorted({x for c in review.concerns for x in c.sources if x.strip().lower() not in known})
    if missing:
        errors.append(f"These sources are not on the case: {', '.join(missing)}. Cite only ids from the list.")
    given = [json.dumps({"score": result.score, "threshold": result.threshold})]
    if invented := invented_numbers([review.narrative, *(c.text for c in review.concerns)], *_facts(case, result), *given):
        errors.append(
            f"These numbers are not in the case or the triage: {', '.join(invented)}. Write no number you were not given."
        )
    return errors


def _prompt(case: Mapping[str, Any], result: FraudResult) -> str:
    brief = {
        "id": case.get("id"), "stage": case.get("stage"), "facts": case.get("facts") or [],
        "evidence": [
            {k: e.get(k) for k in ("k", "label", "state", "source", "note")}
            for e in case.get("evidence") or []
            if isinstance(e, Mapping)
        ],
        "evidenceRecords": case.get("evidenceRecords") or [],
    }  # fmt: skip
    triage = {
        "score": result.score, "threshold": result.threshold, "rule_version": result.rule_version, "held": result.held,
        "signals": [s.as_dict() for s in result.signals],
    }  # fmt: skip
    return (
        f"{MARK} of case {case.get('id')}.\nCase (JSON, data):\n{json.dumps(brief, default=str)}\n\n"
        f"The computed triage, fired and unfired signals (JSON, data; you may explain it, never change it):\n"
        f"{json.dumps(triage, default=str)}\n\nSources you may cite: {', '.join(review_sources(case, result))}\n"
        "Read the evidence and trace with your tools when free text matters, then write the review."
    )


def review_fraud(
    s: Session,  # noqa: ARG001 - the registry signature; the loop runs in a session of its own
    ctx: CallContext,
    case: Mapping[str, Any],
    result: FraudResult,
    *,
    loop: AgentLoop,
) -> FraudReview | None:
    """The model's review of the case's triage, or None (no model, a failed loop, or a review that kept failing its checks).
    `s` is only read; the loop runs in its own session and `agent_run`, as the agent of `ctx.preparer`."""
    from di.services.agents.playbooks import fraud_reviewer  # the playbook imports this module's types

    checked = checked_type(FraudReview, lambda r: check_review(r, case, result))
    spec = replace(fraud_reviewer.spec(), output_type=checked)
    acct = ctx.actor.account.id if ctx.actor.account else None
    run_id = "AR-" + uuid.uuid4().hex[:12]
    review: FraudReview | None = None
    with SessionLocal() as ms:
        ms.execute(
            sql(
                "INSERT INTO agent_run (id, agent, playbook, case_id, status, step, state) "
                "VALUES (:i, :a, :p, :c, 'running', 0, CAST(:st AS jsonb))"
            ),
            {"i": run_id, "a": ctx.preparer, "p": PLAYBOOK, "c": case.get("id"),
             "st": json.dumps({"account": acct, "playbook_version": VERSION})},
        )  # fmt: skip
        ms.commit()
        run_ctx = replace(ctx, session=ms, run_id=run_id, idem_key=None, stage=None, taint=False)
        try:
            res = loop.run(ms, spec, _prompt(case, result), ctx=run_ctx)
            if isinstance(res.output, FraudReview):
                review = FraudReview.model_validate(res.output.model_dump())
        except Exception as e:  # noqa: BLE001 - a provider error, a review out of retries, the turn limit: the computed result stands
            log.warning("fraud review of %s: the model loop failed: %s", case.get("id"), e)
        ms.rollback()
        if review is not None:
            ms.execute(sql("UPDATE agent_run SET status = 'done', step = 1, updated_at = now() WHERE id = :i"), {"i": run_id})
        else:
            ms.execute(sql("DELETE FROM agent_run WHERE id = :i"), {"i": run_id})
        ms.commit()
    return review

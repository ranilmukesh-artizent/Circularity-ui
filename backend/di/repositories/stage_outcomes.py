"""The labels a stage's confidence is calibrated on (plan 9, P9-2.9; story X-05) and the active calibration steps.

Owns: `rows(s, pack, stage)`, the points `(raw confidence, label)` of a pack's stage, and `active_steps`.
  label 1: a proposal of the stage's actions that a person accepted, or a decision approved as the agent submitted it.
  label 0: a proposal rejected, or a decision overridden (`decision.override`).
The raw confidence is the one on the stage's record (`agent_stage_record.confidence`), before any calibration. A pack's
cases are those of its template (`case_record`; no template means industrial).
Never does: fit anything (`di.services.agents.calibrate`) or write a row.
"""

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.repositories import model_versions

_TEMPLATE = "coalesce(c.data->>'template', 'industrial')"

_PROPOSALS = f"""
SELECT r.confidence::float AS conf, CASE p.status WHEN 'accepted' THEN 1 ELSE 0 END AS label
FROM agent_stage_record r
JOIN agent_proposal p ON p.run_id = r.run_id AND p.case_id = r.case_id AND p.action = ANY(:actions)
JOIN case_record c ON c.id = r.case_id
WHERE r.stage = :stage AND r.confidence IS NOT NULL AND p.status IN ('accepted', 'rejected') AND {_TEMPLATE} = :pack
ORDER BY r.at, r.run_id
"""  # noqa: S608 - fixed text; values are bound

# a disposition record with no decided proposal is judged by the first decision on its case after it
_DECISIONS = f"""
SELECT r.confidence::float AS conf, CASE d.action WHEN 'decision.approve' THEN 1 ELSE 0 END AS label
FROM agent_stage_record r
JOIN case_record c ON c.id = r.case_id
JOIN LATERAL (
    SELECT j.action FROM action_journal j
    WHERE j.case_id = r.case_id AND j.action IN ('decision.approve', 'decision.override') AND NOT j.undone AND j.at >= r.at
    ORDER BY j.seq LIMIT 1
) d ON true
WHERE r.stage = 'disposition' AND :stage = 'disposition' AND r.confidence IS NOT NULL AND {_TEMPLATE} = :pack
  AND NOT EXISTS (
    SELECT 1 FROM agent_proposal p WHERE p.run_id = r.run_id AND p.case_id = r.case_id AND p.status IN ('accepted', 'rejected')
  )
ORDER BY r.at, r.run_id
"""  # noqa: S608 - fixed text; values are bound


def template_key(pack: str, stage: str) -> str:
    """The `model_version.template` of a stage's calibration."""
    return f"{pack}.stage.{stage}"


def rows(s: Session, pack: str, stage: str) -> list[tuple[float, int]]:
    """The labelled points of the pack's stage."""
    from di.services.agents.stages import CHAIN  # lazy: the stage modules import repositories

    actions = [a for m in CHAIN if stage == m.ID for a in m.ACTIONS]
    out: list[tuple[float, int]] = []
    for sql, extra in ((_PROPOSALS, {"actions": actions}), (_DECISIONS, {})):
        for r in s.execute(text(sql), {"pack": pack, "stage": stage, **extra}).mappings():
            out.append((float(r["conf"]), int(r["label"])))
    return out


def steps_of(factors: list[dict[str, Any]]) -> list[tuple[float, float]]:
    """Stored `[{raw, cal}]` as steps."""
    return [(float(f["raw"]), float(f["cal"])) for f in factors]


def active_steps(s: Session, pack: str, stage: str) -> list[tuple[float, float]] | None:
    """The steps of the pack stage's active calibration, or None (the stage keeps its raw confidence)."""
    m = model_versions.active(s, template_key(pack, stage))
    return steps_of(m.factors) if m else None

"""The case autopilot playbook (plan 8, MVP-11.5): take one case from its evidence to an approved, sent decision,
with existing actions only, a person approving where one must.

Since plan 9 (P9-2.1) the steps are served by the stage modules (`di.services.agents.stages`), walked by the
`stage_chain` playbook; `case_autopilot` is an alias that runs the same chain with the same calls in the same order and
the run's own agent as the preparer (the legacy flag keeps the stage reads, such as `case.routes`, out of its journal):

    0 evidence    case.evidence                    intake: read; notes whether any evidence item is not ready
    1 request     evidence.request                 intake: only if evidence is missing
    2 reevaluate  case.reevaluate                  valuation: only if the case waits for re-evaluation
    3 submit      decision.submit                  disposition: only if the case awaits approval and is not submitted
                                                   yet; for an agent with autonomy "propose" it holds for a person
    4 approval    wait until a person approves     disposition: the run waits; decision.approve wakes it
    5 resend      instruction.resend               follow_through: only if an instruction to a system failed
    6 done

This module keeps `NAME`, `ACTIONS`, `STEPS` and the four answers a step gives: a Call, a Skip (not needed for this
case), a Wait (for a person), Done (the stage is finished; `skipped` when it had nothing to do) or Halt (the run ends
with a note). Pure.
"""

from dataclasses import dataclass
from typing import Any

NAME = "case_autopilot"
ACTIONS = ("case.evidence", "evidence.request", "case.reevaluate", "decision.submit", "instruction.resend")
STEPS = ("evidence", "request", "reevaluate", "submit", "approval", "resend", "done")


@dataclass(frozen=True)
class Call:
    action: str
    input: dict[str, Any]


@dataclass(frozen=True)
class Skip:
    why: str


@dataclass(frozen=True)
class Wait:
    reason: str


@dataclass(frozen=True)
class Done:
    note: str
    skipped: bool = False


@dataclass(frozen=True)
class Halt:
    note: str


Next = Call | Skip | Wait | Done | Halt

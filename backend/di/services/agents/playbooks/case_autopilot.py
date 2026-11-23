"""The case autopilot playbook (plan 8, MVP-11.5): take one case from its evidence to an approved, sent decision,
with existing actions only, a person approving where one must.

    0 evidence    case.evidence                    read; notes whether any evidence item is not ready
    1 request     evidence.request                 only if evidence is missing
    2 reevaluate  case.reevaluate                  only if the case waits for re-evaluation
    3 submit      decision.submit                  only if the case awaits approval and is not submitted yet; for an
                                                   agent with autonomy "propose" it holds for a person (a proposal)
    4 approval    wait until a person approves     the run waits; decision.approve wakes it (runtime.resume_waiting)
    5 resend      instruction.resend               only if an instruction to a system failed
    6 done

`next_step` says what the step is: a Call, a Skip (not needed for this case), a Wait (for a person) or Done.
`record` keeps what a step's output tells later steps. Pure: the runtime reads the case and runs the calls.
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


Next = Call | Skip | Wait | Done


def next_step(n: int, st: dict[str, Any], case: dict[str, Any], failed_instruction: bool) -> Next:
    """Step `n` for this case. `st` is the run's state, `case` the case as the store holds it."""
    cid = {"case_id": case["id"]}
    name = STEPS[n] if n < len(STEPS) else "done"
    if name == "evidence":
        return Call("case.evidence", cid)
    if name == "request":
        return Call("evidence.request", cid) if st.get("missing") else Skip("no evidence missing")
    if name == "reevaluate":
        return Call("case.reevaluate", cid) if case.get("stage") == "reeval" else Skip("not waiting for re-evaluation")
    if name == "submit":
        if case.get("approval"):
            return Skip("already approved")
        if case.get("stage") != "awaiting_approval":
            return Done(f"{case['id']} is not ready for approval")
        return Skip("already submitted") if case.get("submitted") else Call("decision.submit", cid)
    if name == "approval":
        return Skip("approved") if case.get("approval") else Wait("approval")
    if name == "resend":
        return Call("instruction.resend", cid) if failed_instruction else Skip("no failed instruction")
    return Done("playbook finished")


def record(n: int, output: dict[str, Any], st: dict[str, Any]) -> None:
    """What a step's output tells the later steps."""
    if STEPS[n] == "evidence":
        st["missing"] = any(e.get("state") != "ready" for e in output.get("items") or [])

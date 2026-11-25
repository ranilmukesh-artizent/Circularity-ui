"""The stage-chain playbook (plan 9, P9-2.1; registry entry I-7): walk `CHAIN` one step at a time.

The run state holds `{stage: index into CHAIN, sub: step within the stage}`. `next_step` asks the current stage module
what its step is (a Call, Skip, Wait, Done or Halt, the types of `playbooks.case_autopilot`); the runtime runs a call
through the action pipeline as the stage's agent, writes the stage's record and moves the position with `advance_step`
or `advance_stage`. `case_autopilot` runs this same walk (the runtime sets the state's `legacy` flag for it).
Never does: read or write the database, call an action or decide a hold. Pure.
"""

from collections.abc import Mapping
from typing import Any

from di.services.agents.playbooks.case_autopilot import STEPS, Next
from di.services.agents.stages import CHAIN, StageModule

NAME = "stage_chain"
ACTIONS = tuple(dict.fromkeys(a for m in CHAIN for a in m.ACTIONS))
# A run started before the chain existed has no position, only its autopilot step number (case_autopilot.STEPS): the
# stage and sub-step that step is now (the three lifecycle stages of P9-2.20 come before intake).
LEGACY_POSITION = {
    "evidence": (3, 0), "request": (3, 1), "reevaluate": (7, 0), "submit": (8, 0), "approval": (8, 1), "resend": (9, 0),
}  # fmt: skip


def start_state() -> dict[str, int]:
    return {"stage": 0, "sub": 0}


def where(st: Mapping[str, Any], n: int) -> tuple[int, int]:
    """The run's stage index and sub-step (`n` is the run's step counter, used only by a run without a position)."""
    if "stage" in st:
        return int(st["stage"]), int(st.get("sub", 0))
    name = STEPS[n] if n < len(STEPS) else "done"
    return LEGACY_POSITION.get(name, (len(CHAIN), 0))


def module_at(stage: int) -> StageModule | None:
    return CHAIN[stage] if stage < len(CHAIN) else None


def next_step(stage: int, sub: int, st: dict[str, Any], case: Mapping[str, Any]) -> Next | None:
    """The step the stage gives, or None once every stage is done."""
    mod = module_at(stage)
    return mod.next_call(sub, st, case) if mod else None


def advance_step(st: dict[str, Any], stage: int, sub: int) -> None:
    st["stage"], st["sub"] = stage, sub + 1


def advance_stage(st: dict[str, Any], stage: int) -> None:
    st["stage"], st["sub"] = stage + 1, 0


def finish(st: dict[str, Any]) -> None:
    """The run ends: past the last stage."""
    st["stage"], st["sub"] = len(CHAIN), 0

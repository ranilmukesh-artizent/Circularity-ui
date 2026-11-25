"""The twelve stage modules of the chain, in order (plan 9, P9-2.1; registry entry I-7; the first three are P9-2.20, the last
two P9-2.21).

`CHAIN` is the one list the stage-chain playbook walks. A stage module is pure and has this shape (`StageModule`):

    ID            the stage id (`StageId`)
    ACTIONS       the actions the stage may call (checked at import against the forbidden list, runtime.py)
    next_call(n, st, case)   step `n` of the stage: Call | Skip | Wait | Done | Halt (di.services.agents.playbooks.case_autopilot)
    record(n, output, st)    what a call's output tells the later steps (kept in the run state `st`)
    confidence(st, case)     0-1, or None when unknown
    output(st, case)         the stage's output for its record (JSON)
    sources(st, case)        `{fact, source, at}` items the output rests on

Never does: call an action itself, write a row or read a clock; the runtime does.
"""

from collections.abc import Mapping
from types import ModuleType
from typing import Any, Protocol, cast

from di.services.agents.playbooks.case_autopilot import Next
from di.services.agents.stage_context import STAGE_IDS, StageId
from di.services.agents.stages import (
    condition,
    demand,
    disposition,
    fit_for_use,
    follow_through,
    intake,
    lease_end,
    outcome,
    reconcile,
    return_auth,
    transit,
    valuation,
)  # fmt: skip


class StageModule(Protocol):
    ID: StageId
    ACTIONS: tuple[str, ...]

    def next_call(self, n: int, st: dict[str, Any], case: Mapping[str, Any]) -> Next: ...
    def record(self, n: int, output: dict[str, Any], st: dict[str, Any]) -> None: ...
    def confidence(self, st: dict[str, Any], case: Mapping[str, Any]) -> float | None: ...
    def output(self, st: dict[str, Any], case: Mapping[str, Any]) -> dict[str, Any]: ...
    def sources(self, st: dict[str, Any], case: Mapping[str, Any]) -> list[dict[str, Any]]: ...


_MODULES: tuple[ModuleType, ...] = (
    lease_end, return_auth, transit, intake, condition, demand, fit_for_use, valuation, disposition, follow_through,
    outcome, reconcile,
)  # fmt: skip
CHAIN: tuple[StageModule, ...] = tuple(cast(StageModule, m) for m in _MODULES)
if tuple(m.ID for m in CHAIN) != STAGE_IDS:
    raise RuntimeError("the stage modules are not in chain order")

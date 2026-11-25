"""What the action pipeline is told about the stage an agent call belongs to (plan 9, P9-2.1; registry entry I-7).

Owns: the stage vocabulary (`StageId`, `StageKind`, `Autonomy`, `STAGE_IDS`, `LEGACY_STAGE_IDS`) and the `StageContext`
dataclass that
`CallContext.stage` carries (`di.services.actions.pipeline`). `di.services.agents.chain` re-exports the names.
Never does: import the pipeline, the runtime or a stage module, so the pipeline can import this file; decide anything.
P9-2.1 only sets the context; P9-2.4 (the hold check, I-10) is the first reader.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

Autonomy = Literal["recommend", "limits", "alone"]
StageKind = Literal["deterministic", "llm", "queue"]
# `analytics` is the stage `outcome` and `reconcile` replaced (P9-2.21): old stored records still carry it, so it stays a
# readable id, but it is no stage of the chain.
StageId = Literal[
    "lease_end", "return_auth", "transit", "intake", "condition", "demand", "fit_for_use", "valuation", "disposition",
    "follow_through", "outcome", "reconcile", "analytics",
]  # fmt: skip
STAGE_IDS: tuple[StageId, ...] = (
    "lease_end", "return_auth", "transit", "intake", "condition", "demand", "fit_for_use", "valuation", "disposition",
    "follow_through", "outcome", "reconcile",
)  # fmt: skip
LEGACY_STAGE_IDS: tuple[StageId, ...] = ("analytics",)  # stored by runs before P9-2.21; read, never run


@dataclass
class StageContext:
    """The stage of the chain a call is made in, with the numbers the hold policy reads (P9-2.4)."""

    stage: StageId
    autonomy: Autonomy
    confidence: float | None
    threshold: float
    value: Decimal | None
    value_limit: Decimal | None
    bulk_limit: int | None
    guardrail_holds: list[str] = field(default_factory=list)
    model_concerns: list[str] = field(default_factory=list)  # held concerns of earlier stage readings (P9-2.18)

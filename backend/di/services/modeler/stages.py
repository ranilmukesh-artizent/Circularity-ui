"""The seven decision stages and the guardrail types (plan 9, P9-0.11).

Owns: `STAGE_KEYS`, the one definition of the seven stage keys (B §1.2 stages 1-7), their labels, and `GuardType`.
Never does: evaluate anything; these are names only. The pack format (P9-1.1), the gate catalogue (P9-1.2) and the
stage chain (P9-2.1) import it. Implements registry entry I-1's stage vocabulary.
"""

from typing import Literal

StageKey = Literal["receive", "match", "condition", "value", "decide", "execute", "close"]
STAGE_KEYS: tuple[StageKey, ...] = ("receive", "match", "condition", "value", "decide", "execute", "close")
STAGE_LABELS: dict[StageKey, str] = {
    "receive": "Return and receive",
    "match": "Match and verify",
    "condition": "Condition",
    "value": "Value each route",
    "decide": "Decide",
    "execute": "Execute",
    "close": "Close and learn",
}
GuardType = Literal["Compliance", "Data quality", "Threshold", "Approval"]

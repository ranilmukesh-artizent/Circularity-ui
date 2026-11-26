"""Keep, like-life swap or upgrade for each tool of a contract refresh (plan 9, P9-5.2, story CR-02). Pure.

    tool_actions(lines, life, eop, next_term_end, evaluator, market, table) -> list[ToolAction]   one action per tool line
    totals(actions) -> {"keep": n, "swap": n, "upgrade": n}                                       the panel's split
    flag(action) -> str | None                                                                    "life estimate low confidence"
    hold_reason(actions) -> "confidence" | None                                           why the decision waits for a person
    needs(case_id, actions) -> list[Need]                                                 the like-life need of each swap (P9-5.3)

The per-tool choice is the market's decision table `refresh_tool_action` (I-15, P9-4.2), first hit: parts end before the next term
ends -> `upgrade` to the successor; remaining life under 25% -> `swap`; else `keep`. The thresholds are business rules (BR-C1),
so they live in the table and change only through its maker-checker (a market or customer overlay, P9-5.6's levers). The table's
`reason` is a template: `{class}`, `{eop}`, `{term_end}`, `{successor}` and `{rul}` are filled here from computed facts.

Inputs, all passed in: `lines` (`{serial, cls}`), `life` (serial -> `tool_life.LifeResult` of P9-3.9), `eop` (class -> end of
parts and successor from `plm.end_of_parts`, P9-3.3) and `next_term_end` (the contract's term end plus its term months). A tool
with no life result is treated as 100% with Low confidence (nothing is known, so the decision waits). A tool whose life
confidence is Low (GR-13) keeps its action but is flagged, and `hold_reason` says `confidence`.

Never does: read the database or the clock, write text with a model (every sentence is a table template over computed numbers, so
there is no `AgentLoop` step here) or approve anything. Implements no registry entry; it reads I-15 tables.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from di.services.engine import like_life
from di.services.modeler.tables import DecisionTableEvaluator, JdmTable
from di.services.modeler.valuers.tool_life import LifeResult

Action = Literal["keep", "swap", "upgrade"]
ACTIONS: tuple[Action, ...] = ("keep", "swap", "upgrade")
LOW_FLAG = "life estimate low confidence"


@dataclass(frozen=True)
class ToolAction:
    serial: str
    cls: str
    action: Action
    reason: str
    rul_pct: int
    confidence: str
    end_of_parts: date | None
    successor: str | None


def tool_actions(
    lines: Sequence[Mapping[str, Any]],
    life: Mapping[str, LifeResult],
    eop: Mapping[str, tuple[date | None, str | None]],
    next_term_end: date,
    evaluator: DecisionTableEvaluator,
    market: str,
    table: JdmTable,
) -> list[ToolAction]:
    """The action of each line (module docstring), in the order of `lines`."""
    out: list[ToolAction] = []
    for ln in lines:
        serial, cls = str(ln["serial"]), str(ln.get("cls") or ln.get("tool_class") or "")
        lf = life.get(serial)
        rul, conf = (lf.rul_tool, lf.confidence) if lf is not None else (100, "Low")
        ends, successor = eop.get(cls, (None, None))
        before = ends is not None and ends < next_term_end
        r = evaluator.evaluate(
            table,
            {
                "market": market, "rul_pct": rul, "parts_end_before_term": before,
                "cover_type": str(ln.get("cover_type") or "fleet"),
            },
        )  # fmt: skip
        action = str(r.outputs.get("action"))
        if action not in ACTIONS:
            raise ValueError(f"The table refresh_tool_action gave the action {action!r} for {serial}")
        reason = (
            str(r.outputs.get("reason") or "")
            .replace("{class}", cls)
            .replace("{eop}", ends.isoformat() if ends else "an unknown date")
            .replace("{term_end}", next_term_end.isoformat())
            .replace("{successor}", successor or "its successor")
            .replace("{rul}", str(rul))
        )
        out.append(ToolAction(serial, cls, action, reason, rul, conf, ends, successor))
    return out


def totals(actions: Sequence[ToolAction]) -> dict[str, int]:
    """How many tools are kept, swapped and upgraded."""
    return {a: sum(1 for x in actions if x.action == a) for a in ACTIONS}


def flag(a: ToolAction) -> str | None:
    return LOW_FLAG if a.confidence == "Low" else None


def hold_reason(actions: Sequence[ToolAction]) -> Literal["confidence"] | None:
    """`confidence` when any tool's life estimate is Low confidence: a person decides before the proposal goes on."""
    return "confidence" if any(a.confidence == "Low" for a in actions) else None


def needs(case_id: str, actions: Sequence[ToolAction]) -> list[like_life.Need]:
    """One like-life need for each swapped tool (P9-5.3): id `<case>:<serial>`, the class, and the target life, the median of
    the tools kept (`like_life.target`). The assignment itself is `like_life.match`, over every open contract together."""
    tgt = like_life.target(actions)
    return [like_life.Need(f"{case_id}:{a.serial}", case_id, a.cls, tgt) for a in actions if a.action == "swap"]

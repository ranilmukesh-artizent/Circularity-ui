"""Where a test run's cases stopped (plan 9, P9-8.19; G C6; uses registry entry I-16 replay): the pure grouping.

    Trace(item_id, stage, reason)               one past item through the draft flow: `stage` None means it reached a decision
    group(traces, stages) -> [StageStop]        per stage: how many reached it, how many stopped there, why (reason, count)
    sentence(stops, total, decided, labels)     the plain sentence of the counts, composed from the counts alone (no model)
    check_text(text, facts) -> [str]            why a model's wording of the stops is refused (a number or an id no count gives)

A stop reason is one of `missing_field:<model.field>`, `held_record:<code>` (a row the import held), `guardrail:<id>`,
`threshold:<stage>`, or `no_route:<stage>` (the valuer refused the item, or no route was left, and no guardrail says why).
An item that stopped at a stage reached every stage up to it; one that reached a decision reached all of them.
Owns: that arithmetic and the sentence. Never does: run a decision, read the database or call a model; the action
(`di.services.actions.compose`) builds the traces from `decide_case` results (R19), the wording playbook rewrites the sentence
and `check_text` refuses what it may not say (R16).
"""

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

STAGES: tuple[str, ...] = ("receive", "match", "condition", "value", "decide")  # the stages a decision is made through
EXAMPLES = 5  # item ids kept per reason
HELD_KINDS = ("guardrail", "held_record")  # these read "held at", the others "stopped at"


@dataclass(frozen=True)
class Trace:
    item_id: str
    stage: str | None = None
    reason: str | None = None


@dataclass
class StageStop:
    stage: str
    reached: int
    stopped: int
    reasons: list[tuple[str, int]] = field(default_factory=list)
    examples: dict[str, list[str]] = field(default_factory=dict)  # reason -> the first item ids

    def view(self) -> dict[str, object]:
        return {
            "stage": self.stage, "reached": self.reached, "stopped": self.stopped,
            "reasons": [{"reason": r, "count": n, "examples": self.examples.get(r, [])} for r, n in self.reasons],
        }  # fmt: skip


def group(traces: Sequence[Trace], stages: Sequence[str] = STAGES) -> list[StageStop]:
    """One `StageStop` per stage, in order. A stage the list does not know counts as the last one. Reasons are most common
    first, ties by name; each keeps its first `EXAMPLES` item ids in the order the traces came."""
    order = {s: i for i, s in enumerate(stages)}
    last = len(stages) - 1
    where = [(t, order.get(t.stage, last) if t.stage else None) for t in traces]
    out: list[StageStop] = []
    for i, name in enumerate(stages):
        stopped_here = [t for t, at in where if at == i]
        counts = Counter(t.reason or "" for t in stopped_here)
        ex: dict[str, list[str]] = {}
        for t in stopped_here:
            ex.setdefault(t.reason or "", [])
            if len(ex[t.reason or ""]) < EXAMPLES:
                ex[t.reason or ""].append(t.item_id)
        out.append(StageStop(
            name, sum(1 for _, at in where if at is None or at >= i), len(stopped_here),
            sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])), ex,
        ))  # fmt: skip
    return out


def reason_words(reason: str) -> str:
    kind, _, what = reason.partition(":")
    return {
        "missing_field": f"missing field {what}",
        "held_record": f"held record {what}",
        "guardrail": f"guardrail {what}",
        "threshold": f"below the confidence threshold at {what}",
        "no_route": f"no route left at {what}",
    }.get(kind, reason)


def sentence(stops: Sequence[StageStop], total: int, decided: int, labels: Mapping[str, str] | None = None) -> str:
    """`200 past items: 163 reached a decision; 21 stopped at Condition (missing field condition.grade: 21); 16 held at Intake
    (guardrail G-TOOL-REC: 16)`: stages in order, each with its reasons. Every number is a count of the traces."""
    labels = labels or {}
    parts = [f"{decided} reached a decision"]
    for s in stops:
        if not s.stopped:
            continue
        held = all(r.partition(":")[0] in HELD_KINDS for r, _ in s.reasons)
        why = ", ".join(f"{reason_words(r)}: {n}" for r, n in s.reasons)
        parts.append(f"{s.stopped} {'held' if held else 'stopped'} at {labels.get(s.stage, s.stage.capitalize())} ({why})")
    return f"{total} past item{'' if total == 1 else 's'}: " + "; ".join(parts)


_NUMBER = re.compile(r"(?<![\w.-])\d[\d,]*(?:\.\d+)?")
_TOKEN = re.compile(r"\b(?:G-[A-Z0-9-]+|GR-[A-Z0-9-]+|[a-z_]+\.[a-z_]+)\b")


def check_text(text: str, facts: str) -> list[str]:
    """Why a model's wording of the stops is refused (pure): empty, a number that none of the counts (the `facts` text) gives,
    or a guardrail id or `model.field` the stops do not name."""
    errors: list[str] = []
    if not text.strip():
        return ["Write a short explanation."]
    given = {n.replace(",", "") for n in _NUMBER.findall(facts)}
    if bad := sorted({n for n in (m.replace(",", "") for m in _NUMBER.findall(text)) if n not in given}):
        errors.append(f"These numbers are not in the counts: {', '.join(bad)}. Write no number you were not given.")
    if unknown := sorted({t for t in _TOKEN.findall(text) if t not in facts}):
        errors.append(f"These names are not in the counts: {', '.join(unknown)}. Use only names from the counts.")
    return errors

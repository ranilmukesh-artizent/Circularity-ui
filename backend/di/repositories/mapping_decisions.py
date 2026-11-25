"""The person's choices on suggested field mappings (plan 9, P9-8.4; table `mapping_decision`, migration 0054).

Owns: reading and writing the decision rows of a source, and the memory of a vendor family (what people accepted, replaced
or were told by a system owner), which `mapping.suggest` hands to `di.connectors.mapping_suggest.suggest` as `memory`.
Never does: decide anything itself (the actions in di.services.actions.fabric_sources do, for a person), save a mapping
version, or open a work item.

A choice for a source field sets `superseded` on the older rows of that field (same source and resource), so a field has at
most one live row. `asked_owner` rows are questions: they hold `owner`, the question in `reason`, the masked samples and the
work item's id in `answer`; the owner's answer is a new row with `owner` kept, so the owner's word wins in the memory.
"""

from collections.abc import Mapping
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

DECISIONS = ("accepted", "replaced", "accepted_with_rule", "not_needed", "asked_owner")
_COLS = (
    "id, source_id, resource, src, decision, target, rule, confidence, reason, proposed_by, owner, answer, decided_by, decided_at"
)


def family_of(vendor: str) -> str:
    """The vendor's family: its first word, lower case ("Oracle Depot Repair" -> "oracle")."""
    return vendor.split()[0].lower() if vendor.strip() else ""


def _live(s: Session, where: str, args: Mapping[str, Any]) -> list[dict[str, Any]]:
    q = f"SELECT {_COLS} FROM mapping_decision WHERE NOT superseded AND {where} ORDER BY id"  # noqa: S608 - fixed fragments
    return [dict(r) for r in s.execute(text(q), dict(args)).mappings().all()]


def of_source(s: Session, source_id: str) -> list[dict[str, Any]]:
    """The live decisions of a source, oldest first."""
    return _live(s, "source_id = :s", {"s": source_id})


def get(s: Session, decision_id: int) -> dict[str, Any] | None:
    r = s.execute(text(f"SELECT {_COLS}, superseded FROM mapping_decision WHERE id = :i"), {"i": decision_id}).mappings().first()  # noqa: S608 - fixed
    return dict(r) if r else None


def open_questions(s: Session, source_id: str) -> list[dict[str, Any]]:
    """The live `asked_owner` rows of the source: fields still waiting for the system owner."""
    return _live(s, "source_id = :s AND decision = 'asked_owner'", {"s": source_id})


def supersede(s: Session, source_id: str, src: str, resource: str | None) -> list[dict[str, Any]]:
    """Mark the live rows of this field as superseded; the rows are returned (the caller closes the work items of questions)."""
    old = _live(s, "source_id = :s AND src = :f AND coalesce(resource, '') = :r", {"s": source_id, "f": src, "r": resource or ""})
    if old:
        s.execute(text("UPDATE mapping_decision SET superseded = true WHERE id = ANY(:ids)"), {"ids": [o["id"] for o in old]})
    return old


def record(
    s: Session,
    *,
    source_id: str,
    src: str,
    decision: str,
    by: str,
    resource: str | None = None,
    target: str | None = None,
    rule: str | None = None,
    confidence: float | None = None,
    reason: str | None = None,
    proposed_by: str | None = None,
    owner: str | None = None,
    answer: Mapping[str, Any] | None = None,
) -> int:
    """Insert a decision (after the caller superseded the older rows of the field); returns its id."""
    import json

    return int(
        s.execute(
            text(
                "INSERT INTO mapping_decision (source_id, resource, src, decision, target, rule, confidence, reason, "
                "proposed_by, owner, answer, decided_by) VALUES (:s, :res, :f, :d, :t, :ru, :c, :re, :p, :o, "
                "CAST(:a AS jsonb), :by) RETURNING id"
            ),
            {"s": source_id, "res": resource or None, "f": src, "d": decision, "t": target, "ru": rule, "c": confidence,
             "re": reason, "p": proposed_by, "o": owner, "a": json.dumps(answer) if answer is not None else None, "by": by},
        ).scalar_one()
    )  # fmt: skip


def memory_for(s: Session, vendor_family: str) -> dict[str, str]:
    """Source field -> canonical `model.field` that people chose for the sources of the vendor family (see `family_of`).

    `accepted` and `accepted_with_rule` map the field to its target; `replaced` maps it to the corrected target and drops
    the old one (the proposal that was refused: `answer["proposed"]`), so a refused proposal is not made again from memory.
    The system owner's answers (rows with an `owner`) are applied last, so they win. `not_needed` and questions add nothing."""
    ids = s.execute(
        text("SELECT id FROM source_system WHERE lower(split_part(vendor, ' ', 1)) = :f"), {"f": vendor_family.lower()}
    ).scalars().all()  # fmt: skip
    if not ids:
        return {}
    rows = _live(s, "source_id = ANY(:ids) AND decision <> 'asked_owner' AND decision <> 'not_needed'", {"ids": list(ids)})
    memory: dict[str, str] = {}
    for r in sorted(rows, key=lambda r: (r["owner"] is not None, r["id"])):
        if not r["target"]:
            continue
        if r["decision"] == "replaced":
            refused = (r["answer"] or {}).get("proposed")
            if refused and memory.get(r["src"]) == refused:
                del memory[r["src"]]
        memory[r["src"]] = r["target"]
    return memory

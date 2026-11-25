"""PLM reads over the canonical `part` and `bom` models (plan 8, MVP-9.4): where a part is used, an assembly's lines,
and the demand for recovered parts; and (plan 9, P9-3.3) a tool class's rated life per wear component and its end of
parts. Read only.

The keys are per org unit (di.services.canonical.schema.part_key, bom_key: `<org unit or "shared">:<number>`), so two
org units' PLM systems never mix (edge case 4). An assembly is active while its part is released.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.services.canonical.schema import SHARED_ORG, part_key
from di.services.engine.predictor import BomLine

ACTIVE = "released"


@dataclass(frozen=True)
class ComponentRating:
    """One wear component of a tool class, as PLM rates it (A 1.5): hours, share of the tool's life, critical or not."""

    name: str
    rated_life_hours: float
    weight: float
    critical: bool
    source: str  # the source system that wrote the rating (provenance)
    revision: str  # the PLM revision of the part


def _org(org_unit_id: str | None) -> str:
    return org_unit_id or SHARED_ORG


def where_used(s: Session, org_unit_id: str | None, part_number: str) -> list[dict[str, Any]]:
    """The assemblies (of the org unit's PLM data) that use the part: [{parent, parent_revision, qty}], by parent."""
    rows = s.execute(
        text(
            "SELECT data FROM canonical WHERE model = 'bom' AND key LIKE :p AND data->>'child' = :c "
            "ORDER BY data->>'parent', data->>'parent_revision'"
        ),
        {"p": _org(org_unit_id) + ":%", "c": part_number},
    ).scalars()
    return [{"parent": d.get("parent"), "parent_revision": d.get("parent_revision"), "qty": d.get("qty")} for d in rows]


def _parts(s: Session, org_unit_id: str | None, numbers: Iterable[str]) -> dict[str, dict[str, Any]]:
    keys = {part_key(org_unit_id, n): n for n in numbers}
    if not keys:
        return {}
    rows = s.execute(text("SELECT key, data FROM canonical WHERE model = 'part' AND key = ANY(:k)"), {"k": list(keys)}).all()
    return {keys[r.key]: r.data for r in rows}


def demand(s: Session, org_unit_id: str | None, parts: Iterable[str]) -> dict[str, int]:
    """For each part, how many active assemblies use it: the distinct where-used parents whose part is released."""
    out: dict[str, int] = {}
    for p in dict.fromkeys(parts):
        parents = {u["parent"] for u in where_used(s, org_unit_id, p) if u["parent"]}
        state = _parts(s, org_unit_id, parents)
        out[p] = sum(1 for n in parents if (state.get(n) or {}).get("state") == ACTIVE)
    return out


def bom_lines(s: Session, org_unit_id: str | None, parent: str) -> list[BomLine]:
    """The lines of the assembly's newest revision, each with its part's unit cost (0 when PLM has none)."""
    rows = list(
        s.execute(
            text("SELECT data FROM canonical WHERE model = 'bom' AND key LIKE :p ORDER BY key"),
            {"p": part_key(org_unit_id, parent) + "@%"},
        ).scalars()
    )
    if not rows:
        return []
    newest = max(str(d.get("parent_revision") or "") for d in rows)
    lines = [d for d in rows if str(d.get("parent_revision") or "") == newest]
    cost = _parts(s, org_unit_id, [str(d.get("child")) for d in lines])
    return [
        BomLine(
            part=str(d.get("child")),
            qty=float(d.get("qty") or 0),
            unit_cost=float((cost.get(str(d.get("child"))) or {}).get("unit_cost") or 0),
            harvestable=bool(d.get("harvestable")),
        )
        for d in lines
    ]


def _class_rows(s: Session, org_unit_id: str | None, tool_class: str) -> list[tuple[dict[str, Any], str]]:
    """(data, source) of the org unit's PLM parts of the class, by part number; none: the shared rows, else []."""
    for org in dict.fromkeys([_org(org_unit_id), SHARED_ORG]):
        rows = s.execute(
            text(
                "SELECT c.data, (SELECT p.source_id FROM provenance p WHERE p.model = 'part' AND p.key = c.key "
                "AND p.field = 'tool_class' ORDER BY p.source_id LIMIT 1) AS source FROM canonical c "
                "WHERE c.model = 'part' AND c.key LIKE :p AND c.data->>'tool_class' = :c ORDER BY c.data->>'number'"
            ),
            {"p": org + ":%", "c": tool_class},
        ).all()
        if rows:
            return [(r.data, r.source or "") for r in rows]
    return []


def tool_ratings(s: Session, org_unit_id: str | None, tool_class: str) -> list[ComponentRating]:
    """The rated life of each wear component of the tool class: the owner's PLM rows, else the shared, else []."""
    return [
        ComponentRating(
            name=str(d.get("name")),
            rated_life_hours=float(d["rated_life_hours"]),
            weight=float(d.get("criticality_weight") or 0),
            critical=bool(d.get("critical")),
            source=src,
            revision=str(d.get("revision") or ""),
        )
        for d, src in _class_rows(s, org_unit_id, tool_class)
        if d.get("rated_life_hours") is not None
    ]


def end_of_parts(s: Session, org_unit_id: str | None, tool_class: str) -> tuple[date | None, str | None]:
    """When the class's parts end and the successor model: (None, None) when PLM has no end of parts for it."""
    for d, _src in _class_rows(s, org_unit_id, tool_class):
        if d.get("end_of_parts"):
            return date.fromisoformat(str(d["end_of_parts"])), (str(d["successor"]) if d.get("successor") else None)
    return None, None

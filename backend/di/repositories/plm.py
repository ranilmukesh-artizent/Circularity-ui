"""PLM reads over the canonical `part` and `bom` models (plan 8, MVP-9.4): where a part is used, an assembly's lines,
and the demand for recovered parts.

The keys are per org unit (di.services.canonical.schema.part_key, bom_key: `<org unit or "shared">:<number>`), so two
org units' PLM systems never mix (edge case 4). An assembly is active while its part is released.
"""

from collections.abc import Iterable
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.services.canonical.schema import SHARED_ORG, part_key
from di.services.engine.predictor import BomLine

ACTIVE = "released"


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

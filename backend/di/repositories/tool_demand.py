"""Live named demand for the tool fleet (plan 9, P9-3.12, story TF-07): the orders the six paths are valued against.

    named_demand(s, org_unit_id, cls, as_of, *, case_id=None) -> dict   {lease, so, bid, proj, wo, rcq}

Reads the canonical `demand` records the two read-only sources fill (P9-3.1, P9-3.2) for the tool class `cls`, as the valuer's
`dem` (the exact keys `tool_fleet._value` reads): `fleet` renewals and orders (kind `lease`) -> `lease`; `parts` sales orders
(`so`), trade bids (`bid`), pool requests (`proj`, the nearest need first: the valuer takes one) and open repair orders (`wo`,
by part name). `need` and `exp` are whole days from `as_of`. A record counts when

- one of its sources (the provenance of its facts) is the org's, an ancestor's, or bound to no org unit (a source with no
  `source_system` row counts as shared), and it is not one of the queue's tagged orders (`pack`, cases.named_demand);
- its `need_by` (or `expires`) is after `as_of`; a record with none is never offered;
- no approved or executing decision of the org holds it (the recommended route's destination names it), except the decision of
  `case_id` itself, which keeps its own order.

Owns: the read and the mapping. Never does: value anything (the valuer, I-21), plan the queue (di.services.engine.queue, I-5),
read a model or write. `rcq` (the recycler quote) is the case's own: "" here.
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core.orgs import OrgUnit, ancestors
from di.services.modeler.evidence import parse_time
from di.services.modeler.valuers import tool_fleet

HELD_STAGES = ("approved", "executing")
DEFAULT_TERM = 12


def _org_chain(s: Session, org_unit_id: str) -> list[str]:
    rows = s.execute(text("SELECT id, parent_id, kind, name FROM org_unit")).all()
    return ancestors({r[0]: OrgUnit(r[0], r[1], r[2], r[3]) for r in rows}, org_unit_id)


def _day(v: Any) -> date | None:
    t = parse_time(v) if isinstance(v, str) and v else None
    return t.date() if t else None


def _held(s: Session, org_unit_id: str, case_id: str | None) -> set[str]:
    """The ids of the orders the org's approved or executing decisions hold (their recommended route's destination)."""
    rows = s.execute(
        text(
            "SELECT data FROM case_record WHERE owner = :o AND stage = ANY(:st) AND data ->> 'template' = 'tool_fleet' "
            "AND id <> COALESCE(:c, '')"
        ),
        {"o": org_unit_id, "st": list(HELD_STAGES), "c": case_id},
    ).scalars()
    out: set[str] = set()
    for doc in rows:
        i = doc.get("rec_index")
        dest = (doc["routes"][i].get("dest") or {}) if i is not None and doc.get("routes") else {}
        out |= {x.strip() for x in str(dest.get("id") or "").split(",") if x.strip()}
    return out


def _item(kind: str, key: str, d: dict[str, Any], need: int | None, exp: int | None) -> dict[str, Any]:
    who, site = str(d.get("buyer") or ""), str(d.get("site") or "")
    head = {"kind": kind, "id": key, "who": who, "what": "", "when": ""}
    if kind == "lease":
        renew = d.get("renew") if d.get("renew") is not None else bool(d.get("contract_ref"))
        term = int(d.get("term_months") or DEFAULT_TERM)
        return head | {"renew": bool(renew), "site": site, "need": need, "rate": d.get("lease_rate") or 0, "term": term}
    if kind == "so":
        return head | {"site": site, "need": need, "price": d.get("price") or 0}
    if kind == "bid":
        return head | {"gmin": d.get("grade_min") or "C", "exp": exp, "need": exp, "price": d.get("price") or 0}
    return head | {"who": f"{site} tool pool", "site": site, "need": need, "rental": d.get("amount") or 0,
                   "quote": d.get("order_ref") or key}  # fmt: skip


def named_demand(s: Session, org_unit_id: str, cls: str, as_of: datetime, *, case_id: str | None = None) -> dict[str, Any]:
    """The org's live named orders for the tool class (module docstring)."""
    out: dict[str, Any] = {"lease": [], "so": [], "bid": [], "proj": None, "wo": {}, "rcq": ""}
    if cls not in tool_fleet.CLS:
        return out
    today = as_of.date()
    held = _held(s, org_unit_id, case_id)
    parts = {p for p, _ in tool_fleet.CLS[cls]["parts"]}
    rows = s.execute(
        text(
            "SELECT c.key, c.data FROM canonical c WHERE c.model = 'demand' AND c.data ->> 'tool_class' = :cls "
            "AND c.data ->> 'pack' IS DISTINCT FROM 'tool_fleet' AND EXISTS (SELECT 1 FROM provenance p "
            "LEFT JOIN source_system ss ON ss.id = p.source_id WHERE p.model = 'demand' AND p.key = c.key "
            "AND (ss.org_unit_id IS NULL OR ss.org_unit_id = ANY(:orgs))) ORDER BY c.key"
        ),
        {"cls": cls, "orgs": _org_chain(s, org_unit_id)},
    ).all()
    proj: list[tuple[int, dict[str, Any]]] = []
    for key, d in rows:
        kind = d.get("kind")
        end = _day(d.get("expires") if kind == "bid" else d.get("need_by"))
        if key in held or kind not in ("lease", "so", "bid", "proj", "wo") or end is None or end <= today:
            continue
        days = (end - today).days
        if kind == "wo":
            if d.get("part_name") in parts:
                out["wo"].setdefault(d["part_name"], []).append(
                    {"id": key, "who": str(d.get("buyer") or ""), "backorder": bool(d.get("backorder"))}
                )
        elif kind == "proj":
            proj.append((days, _item(kind, key, d, days, None)))
        else:
            out[kind].append(_item(kind, key, d, days, days))
    out["proj"] = min(proj, key=lambda x: x[0])[1] if proj else None
    return out

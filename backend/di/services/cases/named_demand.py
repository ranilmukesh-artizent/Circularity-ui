"""Named demand for the tool-fleet queue (plan 9, P9-1.4): the canonical `demand` records that name an order, as the
tool-fleet valuer's orders.

    for_queue(s, org_unit_id, classes) -> {class: Dem}

A record counts when `demand.pack` is "tool_fleet" and `demand.org_unit` is the org, one of its ancestors, or empty
(shared with every org). Its canonical key is the order's `id`. `demand.kind` says what it is: `lease` (a fleet
renewal or new order: rate from `lease_rate`, term from `proposed_term_months`, a renewal when `contract_ref` is
set), `so` (a sales order), `bid`, `proj` (a tool pool request) or `wo` (a repair order for `demand.part`).
`need_days` and `exp_days` are days from today; a record without them is needed in 30 days. A class with no order
gets an empty `Dem`.

Owns: the read and the mapping. Never does: write the canonical store or plan the queue (di.services.engine.queue).
The canonical store shares the `cases` layer, so no import-linter exception is needed.
"""

from collections.abc import Sequence
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.core.orgs import OrgUnit, ancestors
from di.services.engine.queue import Dem
from di.services.modeler.valuers import tool_fleet

DEFAULT_DAYS = 30
KINDS = ("lease", "so", "bid", "proj", "wo")


def _empty() -> Dem:
    return {"lease": [], "so": [], "bid": [], "proj": None, "wo": {}}


def _units(s: Session) -> dict[str, OrgUnit]:
    rows = s.execute(text("SELECT id, parent_id, kind, name FROM org_unit")).all()
    return {r[0]: OrgUnit(r[0], r[1], r[2], r[3]) for r in rows}


def _days(d: dict[str, Any], key: str) -> int:
    v = d.get(key)
    return DEFAULT_DAYS if v is None else int(v)


def _order(kind: str, key: str, d: dict[str, Any]) -> dict[str, Any]:
    """The valuer's item for one record (the prototype's mkDemand shapes)."""
    who, site = str(d.get("who") or ""), str(d.get("site") or "")
    head = {"kind": kind, "id": key, "who": who, "what": str(d.get("what") or ""), "when": str(d.get("when") or "")}
    need = _days(d, "need_days")
    if kind == "lease":
        rate, term = d.get("lease_rate") or 0, d.get("proposed_term_months") or 12
        own = {"contract": str(d["contract_ref"])} if d.get("contract_ref") else {}  # the contract this renews
        return head | {"renew": bool(d.get("contract_ref")), "site": site, "need": need, "rate": rate, "term": int(term)} | own
    if kind == "so":
        return head | {"site": site, "need": need, "price": d.get("price") or 0}
    if kind == "bid":
        exp = _days(d, "exp_days")
        return head | {"gmin": d.get("gmin") or "C", "exp": exp, "price": d.get("price") or 0}
    return head | {"site": site, "need": need, "rental": d.get("rental") or 0, "quote": d.get("purchase_ref") or key}


def for_queue(s: Session, org_unit_id: str, classes: Sequence[str]) -> dict[str, Dem]:
    """The named orders of the org for each tool class asked for (see the module docstring)."""
    org = set(ancestors(_units(s), org_unit_id))
    out: dict[str, Dem] = {c: _empty() for c in classes}
    rows = s.execute(
        text("SELECT key, data FROM canonical WHERE model = 'demand' AND data ->> 'pack' = 'tool_fleet' ORDER BY key")
    ).all()
    for key, d in rows:
        kind, cls = d.get("kind"), d.get("cls")
        if cls not in out or kind not in KINDS or (d.get("org_unit") or None) not in (None, *org):
            continue
        dem = out[cls]
        if kind == "wo":
            part = d.get("part")
            if part in {p for p, _ in tool_fleet.CLS[cls]["parts"]}:
                dem["wo"].setdefault(part, []).append(
                    {"id": key, "who": d.get("who") or "", "backorder": bool(d.get("backorder"))}
                )
        elif kind == "proj":
            dem["proj"] = dem["proj"] or _order(kind, key, d)
        else:
            dem[kind].append(_order(kind, key, d))
    return out

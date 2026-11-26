"""The trade compliance approval of a resale (plan 9, P9-10.8, stories TN-07 and TN-08; the approval item of registry entry I-20).

    sync(s, case, pack, routes) -> None   open or close the case's `AP-TN-EXP` item to match its export gate

While G-NET-EXP needs approval for the case (`kind` `require_approval`, not passed: the unit's class is controlled or not
confirmed, and a bid is screened clear) one open work item of type `AP-TN-EXP` is for the role of the pack's
`trade_compliance` (the Approver). The table allows the kinds exception, needs_info and step only, so it is stored as an
exception and My work shows it as an approval (`process._view_kind`: a type that starts `AP-`). It shows what the person
decides on: the bid (id, price, quantity, buyer country, the end-user screening and its reference), the classification with
its source (a class that is not confirmed says so, with the class inferred from the part number), and the alternative "keep
as spares" with its value when that route is valued. Its action is the pack's own (rule `AP-TN-EXP` of
`runtime.suggestion_rules`). When the gate no longer needs approval (a class that is not controlled was confirmed, the bid is
gone) the item closes with "No longer needs approval". A case keeps one open item.

Never does: approve, classify, release or screen. `decision.approve` and `decision.override` are a person's (the pipeline
refuses an agent-prepared call, `services/agents/forbidden.py`), and the class is the inventory's or a person's, never derived.
Kinective's Legal team reviews the wording before it is relied on. In the caller's transaction.
"""

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from di.services.engine.routes import Route
from di.services.modeler.evidence import evidence_of
from di.services.modeler.gate_checks.network import EXPORT_EVIDENCE, EXPORT_GATE, export_text
from di.services.modeler.pack import Pack

ITEM_TYPE = "AP-TN-EXP"
KEEP = "keep as spares"
DEFAULT_ACTION = "Confirm the end user; otherwise keep as spares"
OWNER = "trade_compliance"
CLOSED = "No longer needs approval"


def _needs(case: Mapping[str, Any]) -> bool:
    g = next((x for x in case.get("gates") or [] if x["id"] == EXPORT_GATE), None)
    return g is not None and not g["passed"] and g["kind"] == "require_approval"


def _money(v: Any) -> str:
    return f"${float(v):,.0f}"


def _bid_line(bid: Mapping[str, Any]) -> str:
    screening = f"end-user screening {bid.get('screening')}" + (f" (ref {bid['ref']})" if bid.get("ref") else "")
    return (
        f"Bid {bid.get('id')}: {bid.get('qty')} units at {_money(bid.get('unit_price') or 0)} each, buyer country "
        f"{bid.get('country')}, {screening}."
    )


def _alternative(routes: Sequence[Route]) -> str:
    spare = next((r for r in routes if r["id"] == "spare" and not r["excluded"]), None)
    return f"Alternative: {KEEP}" + (f", worth {_money(spare['net'])}." if spare is not None else ".")


def cause_of(case: Mapping[str, Any], routes: Sequence[Route]) -> str:
    """What the approver decides on: the bid, the classification and its source, the alternative."""
    e = evidence_of(case, EXPORT_EVIDENCE)
    value = e.value if e is not None else {}
    return " ".join([_bid_line(value.get("bid") or {}), f"Export {export_text(value)}.", _alternative(routes)])


def sync(s: Session, case: Mapping[str, Any], pack: Pack, routes: Sequence[Route] = ()) -> None:
    """The case's `AP-TN-EXP` item matches its export gate (module docstring)."""
    from di.services.cases import process

    cid = str(case["id"])
    open_id = s.execute(
        text("SELECT id FROM work_item WHERE case_id = :c AND type = :t AND status = 'open' ORDER BY id LIMIT 1"),
        {"c": cid, "t": ITEM_TYPE},
    ).scalar()
    if not _needs(case):
        if open_id is not None:
            process.close_item(s, int(open_id), CLOSED, "system")
        return
    if open_id is not None:
        return
    rule = next((r for r in pack.runtime.suggestion_rules if r.get("id") == ITEM_TYPE), {})
    owner = str(rule.get("owner") or OWNER)
    process.open_item(
        s, kind="exception", case_id=cid, org_unit_id=case.get("owner"), type=ITEM_TYPE,
        title=f"{cid}: trade compliance approval before resale", cause=cause_of(case, routes),
        action=str(rule.get("action") or DEFAULT_ACTION), owner_role=pack.roles.get(owner, owner),
        due_hours=pack.runtime.sla_hours.get("approval"), by="system",
    )  # fmt: skip
